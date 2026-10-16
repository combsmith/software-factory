"""PreToolUse on an edit or a Bash command: what is the Maintainer's to decide is asked of the person.

Three things are (§5.1, §9.12): an edit to a protected path, one of the Factory's own rules or a
hook that holds them; a merge that bypasses the queue, or a push to the default branch; and a write
to a ruleset or to the repo's settings. For each the hook answers "ask", and the person answers.
That the Maintainer asked is never inferred from the conversation. An enqueue is not asked about:
the Maintainer's standing approval covers it. The hook allows nothing and refuses nothing: what it
does not ask about goes through the session's own permissions. The paths, the commands, the
mutations and the endpoints are data, in `config/hooks.json`.

This hook guards against mistakes; it is not the boundary, which is the rulesets and the
Maintainer's reading of each pull request. It reads plain spellings of a command. A spelling it
cannot read within its budget (a length, and a deadline well inside the settings' timeout) it asks
about, and one it misreads is caught by state: `rules_changed.py` lists, at every stop, each
protected path the branch has changed.

A helper given to git in the command, a program it runs, is asked about unless it is cat or less
read-only. One that runs a script (core.pager='sh x.sh') is decided (decision 0017): it is asked
about as any program is, since the hook reads words, never a file. A fetch whose refspec writes
under refs/heads/ moves a local branch, and asks, unless it writes no ref (--dry-run, --prefetch); a
destination's refs/, heads/, tags/ and remotes/ are read in any case. GIT_OBJECT_DIRECTORY and
GIT_INDEX_FILE set in the command, before git or given to a wrapper that runs it, are places git
writes, read as paths the command writes from where git runs (its -C); an alternate's objects are
read, never written. A variable set before a program is set for that program alone; one set alone,
or by export and the like, holds for what follows until unset.

A protected path is protected in the project and in each worktree under `.claude/worktrees/`, and,
outside them, wherever a path's last parts are a protected path, since another clone's branch can
merge here. A path is read as it is written, normalised, and as the file system resolves it,
symbolic links followed, and compared without regard to case. The hook reads the file system and
git's state only inside the project, resolved: what lies outside it is read by its words alone, and
a decision that needs git's state there (where a push goes) asks. What the hook says names no word of the command:
only codes, and text from config/hooks.json. Run as `python3 -I` on this file; see after_edit.py.
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
from urllib.parse import urlsplit

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT))
from tools.hooks import identity, shell  # noqa: E402

DEADLINE = 5.0          # seconds to read one tool call; the settings give the hook 30
LONGEST = 256 * 1024    # characters of a command the hook reads
LONGEST_PATH = 4096     # characters of a path
NAME = 255              # characters of one name in a path
MATCHES = 2000          # paths one wildcard may match
FILE_TOOLS = {"Edit": "file_path", "Write": "file_path", "MultiEdit": "file_path", "NotebookEdit": "notebook_path"}
SHOWN = 6               # reasons put in front of the person
GLOB = re.compile(r"[*?\[]")
VARIABLE = re.compile(r"\$(?:\{([A-Za-z_]\w*)\}|([A-Za-z_]\w*))")
ASSIGNMENT = identity.ASSIGNMENT
PREFIXES, WRAPPERS = shell.PREFIXES, shell.WRAPPERS
# Programs that read the paths they are named and write none of them. A redirection is read apart from them.
READS = {"cat", "less", "more", "head", "tail", "wc", "grep", "egrep", "fgrep", "rg", "ls", "stat", "file", "diff",
         "cmp", "readlink", "realpath", "basename", "dirname", "test", "[", "[[", "echo", "printf", "true", "false",
         ":", "jq", "nl", "od", "hexdump", "md5", "md5sum", "shasum", "sha1sum", "sha256sum", "cksum", "du", "cut",
         "tr", "comm", "paste", "column", "fold", "strings", "which", "type", "pwd", "sleep", "export", "unset", "set",
         "local", "declare", "readonly", "read", "shift", "exit", "return", "wait", "case", "esac", "fi", "done",
         "cd", "pushd", "popd"}
# Programs that read the paths they are named, and write the value of these options.
OUTPUTS = {"sort": {"-o", "--output"},
           "pytest": {"--junitxml", "--junit-xml", "--basetemp", "--result-log", "--report-log", "--html"},
           "py.test": {"--junitxml", "--junit-xml", "--basetemp", "--result-log", "--report-log", "--html"}}
# Modules `python -m` runs that read the paths they are named: the program whose outputs they share, and the
# position from which their words are written (json.tool's second word is where it writes).
PY_READERS = {"unittest": ("", None), "pytest": ("pytest", None), "json.tool": ("", 1), "doctest": ("", None),
              "pydoc": ("", None), "tabnanny": ("", None), "pyclbr": ("", None)}
# Programs that run code they are given; a here-document they read is code, not data.
INTERPRETERS = re.compile(r"^(python[\d.]*|node|nodejs|deno|bun|perl|ruby|php|lua|osascript|Rscript|awk|gawk|"
                          r"mawk|nawk|bash|sh|zsh|dash|ksh|fish|source|\.)$")
# Programs that write the paths of a list they read on stdin, or into the directory they run in.
FEEDERS = {"xargs", "parallel"}
FEED_VALUED = {"-I", "-L", "-n", "-P", "-s", "-d", "-E", "-a", "--max-args", "--max-procs", "--delimiter",
               "--arg-file", "--max-lines", "--replace", "--eof", "-j", "--jobs"}
# Options after which an interpreter's next word is code or a module, not a script file it reads.
CODE_FOLLOWS = {"-c", "-e", "-E", "--eval", "-p", "--print", "-m", "-r", "--require"}
UNPACKERS = {"tar", "unzip", "cpio", "patch", "bsdtar", "7z", "ditto"}
FIND_WRITES = {"-delete", "-fprint", "-fprint0", "-fprintf", "-fls"}
FIND_RUNS = {"-exec", "-execdir", "-ok", "-okdir"}
# git commands that write no file of the working tree they are named; the rest may.
GIT_READS = {"add", "annotate", "blame", "branch", "cat-file", "check-attr", "check-ignore", "cherry", "commit",
             "count-objects", "describe", "diff", "diff-files", "diff-index", "diff-tree", "fetch", "for-each-ref",
             "fsck", "gc", "grep", "help", "log", "ls-files", "ls-remote", "ls-tree", "maintenance", "merge-base",
             "name-rev", "prune", "push", "range-diff", "reflog", "remote", "repack", "rev-list", "rev-parse",
             "shortlog", "show", "show-branch", "show-ref", "status", "tag", "var", "verify-commit", "verify-tag",
             "version", "whatchanged", "worktree"}
GIT_READS |= {"check-mailmap", "check-ref-format", "get-tar-commit-id", "merge-tree", "patch-id", "show-index",
              "verify-pack"}    # plumbing that reads; and commit-graph when it verifies, in _git
GIT_VALUED = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env"}
# Environment that names a place git writes, for any command: True for a list of directories, False for a file.
# GIT_ALTERNATE_OBJECT_DIRECTORIES is not one: git reads an alternate's objects and never writes them.
GIT_WRITE_ENVIRONMENT = {"GIT_OBJECT_DIRECTORY": True, "GIT_INDEX_FILE": False}
# Every git command the hooks know: another is an alias, or an extension, which the hook cannot read.
GIT_KNOWN = identity.WRITES | identity.RUNNERS | identity.OTHERS | GIT_READS | {"symbolic-ref", "update-ref"}
PUSH_VALUED = {"-o", "--push-option", "--receive-pack", "--exec", "--repo"}
# A helper given in the command: a program git runs, which the hook does not read. git configuration whose value is
# the program, one list with identity.py's; configuration that always asks, since it loads code from a place or
# names a program git finds (credential.helper=cat runs git-credential-cat); options and environment that name it.
GIT_HELPER_KEYS = identity.PROGRAM_KEYS
GIT_HELPER_LOADS = identity.LOAD_KEYS
# Options that name the program, or always ask, are identity.py's HELPER_OPTIONS, read by identity.programs_given.
GIT_HELPER_ENV = re.compile(r"^(GIT_EXTERNAL_DIFF|GIT_PAGER|PAGER|GIT_EDITOR|GIT_SEQUENCE_EDITOR|EDITOR|VISUAL|GIT_SSH|"
                            r"GIT_SSH_COMMAND|GIT_ASKPASS|SSH_ASKPASS|GIT_PROXY_COMMAND)$")
GIT_HELPER_ENV_LOADS = re.compile(r"^(GIT_ALLOW_PROTOCOL|GIT_CONFIG_PARAMETERS|GIT_CONFIG_COUNT|GIT_CONFIG_GLOBAL|"
                                  r"GIT_CONFIG_SYSTEM|GIT_CONFIG|GIT_EXEC_PATH|GIT_TEMPLATE_DIR)$")
# A helper that only reads lets the hook pass it: these programs, by their bare name. less is one only without an
# option that writes a file or runs or loads commands, and without its environment set in the command.
# less takes a long option by any prefix, and in either case, since --LOG-FILE is -O as --log-file is -o.
HELPER_READERS = {"cat", "less"}
LESS_WRITES = re.compile(r"^(\+|-[^-]*[oOk])")
LESS_WRITES_LONG = ("--log-file", "--lesskey", "--lesskey-src", "--lesskey-content")
# Where a push with no refspec goes is read exactly only under these; any other push.default may reach main.
PUSH_DEFAULTS = {None, "simple", "current"}
# git configuration that says where a push goes.
PUSH_KEYS = re.compile(r"^(push\.|remote\..*\.push$|branch\..*\.(merge|remote)$)", re.I | re.S)
# What branch and tag do when given these: list, show or delete, and write no new name.
REF_READS = {"-l", "--list", "-a", "--all", "-r", "--remotes", "-d", "-D", "--delete", "-v", "-vv", "--verbose",
             "--show-current", "--contains", "--no-contains", "--merged", "--no-merged", "--points-at", "-n",
             "--sort", "--format", "--column", "--verify"}
REMOTE_REF = "refs/remotes/"
LOCAL_REF = "refs/heads/"
# Configuration that holds the refspecs a fetch with none of its own follows.
FETCH_KEYS = re.compile(r"^remote\..+\.fetch$", re.I | re.S)
# fetch's and pull's options that take the next word as their value, long and short, and the short ones whose value
# is only what is attached (pull -rmerges, -Skeyid), as identity.py reads them; the shortest prefixes of --refmap and
# --stdin that no other of their options shares (--ref is also --refetch, --st also --stat); and of the options with
# which a fetch writes no ref, or none but under refs/prefetch/ (--d is also --depth, --pr also --prune).
FETCH_VALUED = identity.FETCH_VALUED
FETCH_SHORT_VALUED, FETCH_SHORT_OPTIONAL = identity.FETCH_SHORT_VALUED, identity.FETCH_SHORT_OPTIONAL
FETCH_REFMAP, FETCH_STDIN = "--refm", "--std"
GH_VALUED = {"-R", "--repo", "--hostname"}
GH_COMMANDS = {"accessibility", "agent-task", "alias", "api", "attestation", "auth", "browse", "cache", "co",
               "codespace", "completion", "config", "copilot", "extension", "ext", "gist", "gpg-key", "help", "issue",
               "label", "org", "pr", "preview", "project", "release", "repo", "ruleset", "run", "search", "secret",
               "ssh-key", "status", "variable", "version", "workflow"}
GH_WRITES_FILES = (["run", "download"], ["release", "download"], ["repo", "clone"], ["gist", "clone"])
API_VALUED = {"-X", "--method", "-H", "--header", "-f", "--raw-field", "-F", "--field", "--input", "-q", "--jq",
              "-t", "--template", "--cache", "-p", "--preview", "--hostname"}
API_FLAGS = {"-i", "--include", "--paginate", "--slurp", "--silent", "--verbose"}
# Text that names a merge or GitHub's API in a program the hook cannot read as gh: gh, then one of these words.
GH_WORD = re.compile(r"\bgh\b")
GH_DOES = re.compile(r"\b(merge|api|ruleset|repo|secret|variable|workflow|alias)\b", re.I)
# A URL is read by its host; outside a URL, GitHub's API is named by its host as a whole word.
URL = re.compile(r"[a-z][a-z0-9+.-]*://[^\s'\"]+", re.I)
API_HOST = re.compile(r"(?<![\w.-])api\.github\.com(?![\w-])", re.I)


class Unreadable(Exception):
    """What the decision rests on could not be read."""


class Spent(Exception):
    """The hook's budget for one tool call ran out."""


class Budget:
    """A deadline for one tool call. Calling it after the deadline raises Spent."""

    def __init__(self, seconds: float):
        self.until = time.monotonic() + seconds

    def __call__(self):
        if time.monotonic() > self.until:
            raise Spent()

    def left(self) -> float:
        return max(0.0, self.until - time.monotonic())


def _glob(pattern: str, segment: str, most: str = "*") -> str:
    """A regular expression for a pattern of names: `*` is any part of one name (`segment` is what a name is made of)."""
    return "".join(segment + most if c == "*" else re.escape(c) for c in pattern)


def load(path: pathlib.Path = ROOT / "config" / "hooks.json") -> dict:
    """The data the hook asks from. Raises Unreadable when it is missing or has not the shape the hook reads."""
    try:
        data = json.loads(path.read_text())
        protected = [(e["path"], e["is"]) for e in data["protected"]]
        reported = [(e["path"], e["is"]) for e in data["reported"]]
        lists = {group: {key: list(data[group][key]) for key in ("commands", "mutations", "endpoints")}
                 for group in ("merging", "settings")}
        lists["settings"]["reads"] = list(data["settings"]["reads"])
        branch = data["merging"]["branch"]
    except (OSError, ValueError, KeyError, TypeError) as err:
        raise Unreadable("config/hooks.json cannot be read (%s)" % type(err).__name__)
    paths = protected + reported
    words = [p for p, _ in paths] + [branch] + [w for group in lists.values() for v in group.values() for w in v]
    if not protected or not all(isinstance(w, str) and w for w in words) or any(".." in p.split("/") for p, _ in paths):
        raise Unreadable("config/hooks.json does not have the shape the hook reads")
    return {"protected": protected, "reported": reported, "branch": branch, **lists}


def entries(listing: list) -> list:
    """Each (path, what) of a list from config/hooks.json, with its parts and a pattern for a whole relative path."""
    out = []
    for path, what in listing:
        parts = path.casefold().rstrip("/").split("/")
        whole = re.compile("/".join(_glob(p, "[^/]") for p in parts) + ("(/.*)?" if path.endswith("/") else "")
                           + r"\Z", re.S)
        out.append((path, what, parts, whole))
    return out


def listed(data: dict, paths: list) -> list:
    """(path, what it is) for each relative path that is protected or reported."""
    every = entries(data["protected"] + data["reported"])
    return [(p, next(what for _, what, _, whole in every if whole.match(p.casefold()))) for p in paths
            if any(whole.match(p.casefold()) for _, _, _, whole in every)]


class Rules:
    """The protected paths, and where to read them from: the top of every working tree that holds a path."""

    def __init__(self, data: dict, env: dict, spend: Budget):
        self.spend = spend
        self.entries, self.named = entries(data["protected"]), []
        for path, what, parts, _ in self.entries:
            # As text, a path is named whole, or a file by its own name, `open("authority.json")`, when that name has
            # an extension: `config`, the name of .git/config, is too common a word to read as a path.
            forms = ["/".join(parts)] + ([parts[-1]] if not path.endswith("/") and len(parts) > 1 and "." in parts[-1]
                                         else [])
            self.named.append((re.compile(r"(?<![\w.-])(%s)(?![\w.-])" % "|".join(
                _glob(f, r"[^/\s'\"]", "{0,%d}" % NAME) for f in forms), re.S), path, what))
        # The one tree whose state the hook reads: the project, resolved once. Its worktrees lie inside it.
        self.root = os.path.realpath(env.get("CLAUDE_PROJECT_DIR") or str(ROOT))
        self.low_root = self.root.casefold()
        self.worktrees = os.path.join(self.low_root, ".claude", "worktrees")

    def names(self, text: str):
        """The protected path that `text` names, as text, wherever it stands; None if none."""
        text = text.casefold().replace("\\", "")
        return next(((path, what) for named, path, what in self.named if named.search(text)), None)

    def inside(self, path):
        """`path` resolved, when it lies in the project; None otherwise. Nothing outside the project is read."""
        return _confined(path, self.root)

    def where(self, path: str, holds: bool = True):
        """(path in config, what it is) for an absolute path that is protected, or that holds one; None otherwise.

        It reads only words, never the file system. In the project, a path is read from the project's top or from
        its worktree's; outside it, a path whose last parts are a protected path is one. `holds` counts a directory
        that holds a protected path, which a command that writes below it can reach.
        """
        for form in dict.fromkeys((os.path.normpath(path), os.path.realpath(path))):
            self.spend()
            low = form.casefold()
            if low == self.low_root or self.low_root.startswith(low.rstrip("/") + "/"):
                if holds:
                    return "a working tree", "a directory that holds every protected path"
                continue
            if not low.startswith(self.low_root + "/"):
                parts = low.strip("/").split("/")
                for at in range(len(parts)):
                    rel = "/".join(parts[at:])
                    found = next(((p, what) for p, what, _, whole in self.entries if whole.match(rel)), None)
                    if found:
                        return found
                continue
            tops = [self.low_root]
            if low.startswith(self.worktrees + "/"):
                tops.append("/".join(low.split("/")[:self.worktrees.count("/") + 2]))
            for top in tops:
                if low == top:
                    if holds:
                        return "a working tree", "a directory that holds every protected path"
                    continue
                rel = low[len(top) + 1:]
                parts = rel.split("/")
                for path_, what, entry, whole in self.entries:
                    if whole.match(rel):
                        return path_, what
                    if holds and len(parts) < len(entry) and all(
                            re.match(_glob(e, "[^/]") + r"\Z", p, re.S) for e, p in zip(entry, parts)):
                        return path_, "a directory that holds %s" % what
        return None

    def hard_linked(self, path: str) -> bool:
        """Whether a file in the project has a second name, which may be protected. Outside the project, not read."""
        real = self.inside(path)
        if real is None:
            return False
        try:
            st = os.stat(real)
        except OSError:
            return False
        return st.st_nlink > 1 and not os.path.isdir(real)

    def is_dir(self, path: str) -> bool:
        """Whether a path in the project is a directory. Outside the project, not read."""
        real = self.inside(path)
        return real is not None and os.path.isdir(real)


# ---- the file tools

def edit(payload: dict, rules: Rules) -> list:
    key = FILE_TOOLS[payload["tool_name"]]
    path = (payload.get("tool_input") or {}).get(key)
    if not isinstance(path, str) or not path:
        return [("path_unreadable", "the edit names no path")]
    if len(path) > LONGEST_PATH:
        return [("budget_spent", "the path is longer than the hook reads")]
    if not os.path.isabs(path):
        cwd = payload.get("cwd")
        if not cwd:
            return [("path_unreadable", "the edit names a relative path, and the session's directory is not given")]
        path = os.path.join(cwd, path)
    found = rules.where(path, holds=False)
    if found:
        return [("protected_path", "%s is %s" % found)]
    if rules.hard_linked(path):
        return [("path_unreadable", "the file has more than one name, and one may be protected")]
    return []


# ---- Bash

class Command:
    """One Bash command read, simple command by simple command, for the paths it writes, a merge and a setting."""

    def __init__(self, text: str, cwd, rules: Rules, data: dict, env: dict):
        self.text, self.rules, self.data, self.spend, self.env = text, rules, data, rules.spend, env
        self.here = os.path.normpath(cwd) if cwd and os.path.isabs(cwd) else None
        self.known = {k: env[k] for k in ("HOME", "TMPDIR", "CLAUDE_PROJECT_DIR") if env.get(k)}
        self.assigned = set()       # the names the command itself sets
        self.found = []

    def ask(self, code: str, sentence: str):
        self.found.append((code, sentence))

    # -- words to paths

    def expand(self, word: str):
        """The word with what the hook knows put in for each variable and ~; None when something is left unknown."""
        known = dict(self.known, PWD=self.here) if self.here else self.known
        out = VARIABLE.sub(lambda m: known.get(m.group(1) or m.group(2), "\0"), word)
        if "\0" in out or "$" in out or "`" in out:
            return None
        if out.startswith("~"):
            if not re.match(r"~(/|$)", out) or "HOME" not in known:
                return None
            out = known["HOME"] + out[1:]
        return out

    def paths(self, word: str, here=None) -> list:
        """The absolute paths a word may name, wildcards expanded as the shell would. Raises Unreadable.

        Braces are not expanded: each brace is read as a wildcard, and a word whose wildcard may name a
        protected path is unreadable.
        """
        here = here or self.here
        word = self.expand(word)
        if word is None:
            raise Unreadable("a path is held in a variable or a command the hook cannot read")
        if len(word) > LONGEST_PATH:
            raise Unreadable("a path is longer than the hook reads")
        if not os.path.isabs(word):
            if here is None:
                raise Unreadable("the directory the command runs in cannot be told from its words")
            word = os.path.join(here, word)
        starred = _starred(word, self.spend)
        if starred != word:
            if any(self.rules.where(p) for p in _wildcards(starred, self.rules)):
                raise Unreadable("a brace may spell a protected path, and the hook does not expand braces")
            return []
        return _wildcards(word, self.rules) if GLOB.search(word) else [word]

    def hit(self, word: str, holds: bool = True, here=None, text: bool = True):
        """What protected path a word names, by where it leads or, with `text`, as text; None if none.

        Raises Unreadable when where it leads cannot be read.
        """
        self.spend()
        values = [word] + ([word.split("=", 1)[1]] if "=" in word[1:] else [])
        if word.startswith("-") and not word.startswith("--") and len(word) > 2:
            values.append(word[2:])         # a short option's value, attached: -olifecycle/x
        named = next((n for n in map(self.rules.names, values) if n), None) if text else None
        if named:
            return named
        for value in values:
            if value.startswith("-") or not value:
                continue
            for path in self.paths(value, here):
                found = self.rules.where(path, holds)
                if found:
                    return found
                if self.rules.hard_linked(path):
                    return "a file with more than one name", "one of them may be protected"
        return None

    def check(self, words: list, holds: bool = True, here=None, text: bool = True) -> bool:
        """Ask about the first of these words, written by a command, that names a protected path. Whether it asked."""
        for word in words:
            try:
                found = self.hit(word, holds, here, text)
            except Unreadable as err:
                self.ask("path_unreadable", "the command is given a path the hook cannot read: %s" % err)
                return True
            if found:
                self.ask("protected_path", "the command may write %s, which is %s" % found)
                return True
        return False

    def into(self, where, here=None) -> bool:
        """Ask if a command writes files it does not name into `where`, or where it runs, and that holds a protected path."""
        here = here or self.here
        try:
            places = self.paths(where, here) if where else ([here] if here else None)
        except Unreadable:
            places = None
        if not places:
            self.ask("path_unreadable", "the command writes into a directory the hook cannot read")
            return True
        for place in places:
            found = self.rules.where(place)
            if found:
                self.ask("protected_path", "the command writes files it does not name into %s, which is %s" % found)
                return True
        return False

    # -- the command

    def read(self) -> list:
        if len(self.text) > LONGEST:
            self.ask("budget_spent", "the command is longer than the hook reads")
            return self.found
        self._seed()
        if ">(" in self.text:
            self.ask("command_unreadable", "a process substitution writes where the hook cannot follow")
        try:
            outer, inner = _process_substitutions(self.text)
            commands = shell.commands(outer, self.spend)
            for script in inner:
                commands += shell.commands(script, self.spend)
        except (ValueError, RecursionError):
            self.ask("command_unreadable", "the command cannot be split into words")
            return self.found
        for at, (words, redirections) in enumerate(commands):
            self.spend()
            if words and words[-1].endswith("=$") and at + 1 < len(commands):
                # Unquoted, D=$(mktemp -d) is read as D=$ and the command inside: put them together again.
                words = words[:-1] + [words[-1] + "(%s)" % " ".join(commands[at + 1][0])]
            self.redirections(redirections)
            if words:
                self.github(words, redirections)
                self.simple(words, redirections)
        return self.found

    def redirections(self, redirections: list):
        for operator, target in redirections:
            if ">" not in operator or (operator.endswith("&") and re.match(r"^(\d+|-)$", target)):
                continue
            try:
                found = self.hit(target, holds=False)
            except Unreadable as err:
                self.ask("path_unreadable", "output is sent to a path the hook cannot read: %s" % err)
                continue
            if found:
                self.ask("protected_path", "output is sent to %s, which is %s" % found)

    def _seed(self):
        """Read what the command sets in the environment, once, before any command is read (shell.trusted_assignments):
        a trusted assignment with its value; any other that may persist (in a condition, a body, a group) named with
        no value; an unset only when it runs unconditionally at the top level before any git or gh, since one after
        a git command came too late for it. A name set in a way the hook cannot read stays named, with no value, so a
        path or a helper that uses it is asked about."""
        for kind, name, value in shell.trusted_assignments(self.text):
            if kind == "unset":
                self.assigned.discard(name)
                self.known.pop(name, None)
            elif kind == "maybe":
                self.assigned.add(name)
                self.known.pop(name, None)
            else:
                self.assign("%s=%s" % (name, value))
        for name in shell.assigned_elsewhere(self.text):      # ${X:=v}, $((X=1)), let X=1
            self.assigned.add(name)
            self.known.pop(name, None)
        off_limits = shell.touched(self.text)
        for name in list(self.known):
            if name not in ("HOME", "TMPDIR", "CLAUDE_PROJECT_DIR") and (name in off_limits or "*" in off_limits):
                self.known.pop(name, None)      # set more than one way, or through eval: its value is not read

    def simple(self, words: list, redirections: list):
        at = 0
        while at < len(words) and (words[at] in PREFIXES or ASSIGNMENT.match(words[at])):
            at += 1
        if at == len(words):
            return      # only assignments: _seed has read the ones that run unconditionally at the top level
        given = [w for w in words[:at] if ASSIGNMENT.match(w)]
        restore = self.assign_for(given)        # before a program, for that program alone
        try:
            self.program(os.path.basename(words[at]), words[at + 1:], redirections)
        finally:
            restore()

    def assign_for(self, words: list):
        """Assign these words for one command; what is returned, called, puts back what was there before."""
        names = [w.split("=", 1)[0] for w in words]
        before = {name: (name in self.assigned, self.known.get(name), name in self.known) for name in names}
        for word in words:
            self.assign(word)

        def restore():
            for name, (was, value, known) in before.items():
                if not was:
                    self.assigned.discard(name)
                if known:
                    self.known[name] = value
                else:
                    self.known.pop(name, None)
        return restore

    def program(self, program: str, args: list, redirections: list):
        if program in ("cd", "pushd", "popd"):
            self.here = None if program == "popd" or (args and args[0] == "-") else self.cd(args[0] if args else "~")
            return
        if program in ("export", "local", "declare", "readonly", "typeset", "unset"):
            return      # _seed has read the assignments and unsets that run unconditionally at the top level
        if program in READS:
            return
        if program in OUTPUTS:
            self.reader(args, OUTPUTS[program])
            return
        if program in shell.SHELLS and any(w.startswith("-") and not w.startswith("--") and "c" in w for w in args):
            return      # the script it runs is read as commands of its own
        if program == "eval":
            return
        if INTERPRETERS.match(program):
            if any("<<" in op and "<<<" not in op for op, _ in redirections):
                found = self.rules.names(self.text)
                if found:
                    self.ask("protected_path", "a script read from a here-document names %s, which is %s, and the "
                                               "hook cannot tell a read from a write" % found)
                    return
            module = args[args.index("-m") + 1] if "-m" in args[:-1] else None
            if module in PY_READERS:
                kind, writes_from = PY_READERS[module]
                self.reader(args[args.index("-m") + 2:], OUTPUTS.get(kind, set()), writes_from)
                return
            args = _without_script(program, args)
        tool = next((i for i, w in enumerate(args) if os.path.basename(w) == "git"), None)
        if program != "git" and tool is not None:
            # A wrapper's git writes where the environment says, too, the wrapper's own assignments among it (env
            # GIT_INDEX_FILE=x git), read from where git runs.
            restore = self.assign_for([w for w in args[:tool] if ASSIGNMENT.match(w)] if program in WRAPPERS else [])
            try:
                asked = self._git_environment(self._git_start(args[tool + 1:], self.here)[0])
            finally:
                restore()
            if asked:
                return
        handler = getattr(self, "_" + program.replace("-", "_"), None) if program in HANDLED else None
        if handler:
            handler(program, args)
        elif program in UNPACKERS:
            self._unpack(program, args)
        elif program in FEEDERS:
            self._feed(args)
        else:
            self.check(args)

    def reader(self, args: list, outputs: set, writes_from=None):
        """A program that reads the paths it is named: only the values of `outputs`, and its words from `writes_from`, are written."""
        written, positional, i = [], [], 0
        while i < len(args):
            option, given, value = args[i].partition("=")
            if option in outputs or (not args[i].startswith("--") and args[i][:2] in outputs and len(args[i]) > 2):
                if not given and option in outputs:
                    i += 1
                    value = args[i] if i < len(args) else ""
                elif not given:
                    value = args[i][2:]
                written.append(value)
            elif not args[i].startswith("-"):
                positional.append(args[i])
            i += 1
        if writes_from is not None:
            written += positional[writes_from:]
        self.check(written, holds=False)

    def assign(self, word: str):
        name, value = word.split("=", 1)
        self.assigned.add(name)
        inner = re.match(r"^(?:\$\((.*)\)|`(.*)`)$", value, re.S)
        if inner and re.match(r"^mktemp(\s+(-d|-q|-u|-t\s+\S+))*\s*$", (inner.group(1) or inner.group(2)).strip()):
            self.known[name] = os.path.join(self.known.get("TMPDIR") or tempfile.gettempdir(), "mktemp")
            return
        expanded = self.expand(value)
        if expanded is None:
            self.known.pop(name, None)      # left unknown, so a path that uses it is asked about
        else:
            self.known[name] = expanded

    def cd(self, word: str):
        try:
            places = self.paths(word)
        except Unreadable:
            return None
        return os.path.normpath(places[0]) if len(places) == 1 else None

    # -- programs read by what they do

    def _sed(self, program: str, args: list):
        if any(w.startswith("--in-place") or (w.startswith("-") and not w.startswith("--") and "i" in w)
               for w in args):
            self.check(args)
            return
        for word in args:       # a script names what it writes as text; a file it reads leads somewhere
            named = self.rules.names(word)
            if named:
                try:
                    lead = any(self.rules.where(p, holds=False) for p in self.paths(word))
                except Unreadable:
                    lead = False
                if not lead:
                    self.ask("protected_path", "a sed script names %s, which is %s" % named)
                    return

    def _find(self, program: str, args: list):
        runs = [args[i + 1] for i, w in enumerate(args[:-1]) if w in FIND_RUNS]
        if FIND_WRITES & set(args) or any(os.path.basename(r) not in READS for r in runs):
            self.check(args)

    def _cp(self, program: str, args: list):
        """cp, mv and install write their target; mv also takes away what it moves."""
        positional, target, as_file, i = [], None, False, 0
        while i < len(args):
            word = args[i]
            if word == "--":
                positional += args[i + 1:]
                break
            option, given, value = word.partition("=")
            if option in ("-t", "--target-directory", "-S", "--suffix", "-m", "--mode", "-o", "--owner", "-g",
                          "--group"):
                if not given:
                    i += 1
                    value = args[i] if i < len(args) else ""
                if option in ("-t", "--target-directory"):
                    target = value
            elif word in ("-T", "--no-target-directory"):
                as_file = True
            elif not word.startswith("-") or word == "-":
                positional.append(word)
            i += 1
        if target is None:
            if not positional:
                return
            target, positional = positional[-1], positional[:-1]
        if program == "mv" and self.check(positional):
            return
        try:
            places = self.paths(target)
        except Unreadable as err:
            self.ask("path_unreadable", "the command is given a target the hook cannot read: %s" % err)
            return
        for place in places:
            if self.rules.inside(place) is None:
                # Outside the project, a file and a directory are not told apart: the place is read by its own words,
                # and as a directory that may hold the project.
                if self.check([place]):
                    return
                continue
            if as_file or not (self.rules.is_dir(place) or target.endswith("/")):
                if self.check([place], holds=False):
                    return
                continue
            for source in positional:      # into a directory: each source by its own name
                name = os.path.basename(source.rstrip("/"))
                if source.endswith("/") or name in (".", ""):
                    into = place            # what is in the source, not the source itself
                elif self.expand(name) is None or _starred(name, self.spend) != name:
                    into = os.path.join(place, "*")     # a name the hook cannot read may be any name there
                else:
                    into = os.path.join(place, name)
                if self.check([into]):
                    return

    _mv = _install = _cp

    def _git_start(self, args: list, here) -> tuple:
        """(where git runs, by each -C, the index of its command in `args`, whether it is pointed at another tree)."""
        i, tree_unknown = 0, False
        while i < len(args) and args[i].startswith("-"):
            option, given, value = args[i].partition("=")
            if option in GIT_VALUED and not given:
                i += 1
                value = args[i] if i < len(args) else ""
            if option == "-C":
                here = self.cd_from(value, here)
            elif option in ("--git-dir", "--work-tree"):
                tree_unknown = True
            i += 1
        return here, i, tree_unknown

    def _git(self, program: str, args: list):
        here, i, tree_unknown = self._git_start(args, self.here)
        sub, rest = (args[i], args[i + 1:]) if i < len(args) else ("", [])
        if self._git_environment(here):
            return
        if sub in GIT_READS or (sub, rest[:1]) == ("commit-graph", ["verify"]):     # but --output writes a file
            outputs = [rest[j + 1] if w == "--output" and j + 1 < len(rest) else w[len("--output="):]
                       for j, w in enumerate(rest) if w == "--output" or w.startswith("--output=")]
            self.check(outputs, holds=False, here=here, text=False)
            return
        if tree_unknown:
            self.ask("path_unreadable", "git is pointed at a working tree the hook does not read")
            return
        if sub in ("apply", "am") or (sub == "stash" and rest[:1] in (["pop"], ["apply"])):
            self.into(None, here)       # what it writes is in a patch or a stash, which the hook does not read
            return
        if any(w.startswith(":") for w in rest):
            self.ask("path_unreadable", "git is given a pathspec with magic the hook does not read")
            return
        # git matches a pathspec's wildcards across directories: read one as the directory it starts in.
        globbed = [w[:GLOB.search(w).start()].rpartition("/")[0] or "." for w in rest
                   if GLOB.search(w) and not w.startswith("-")]
        if not self.check(globbed, here=here, text=False):
            self.check(rest, here=here, text=False)

    def _git_environment(self, here) -> bool:
        """Ask if the command sets, for git, a place it writes: its objects, an alternate's, or its index. Even a git
        that reads writes them (commit-graph write, an index refreshed). A relative place is read from where git runs
        and from each directory above, since git may move to the top of its tree first. Whether it asked."""
        for name, directories in GIT_WRITE_ENVIRONMENT.items():
            if name not in self.assigned:
                continue
            value = self.known.get(name)
            if value is None:
                self.ask("path_unreadable", "git is told to write its objects or its index where the hook cannot read")
                return True
            for path in value.split(os.pathsep) if directories else [value]:
                starts = [None] if os.path.isabs(path) else [
                    str(top) for start in dict.fromkeys((self.here, here)) if start
                    for top in [pathlib.PurePath(start)] + list(pathlib.PurePath(start).parents)] or [None]
                if path and any(self.check([path], holds=directories, here=start) for start in starts):
                    return True
        return False

    def cd_from(self, word: str, here):
        try:
            found = self.paths(word, here)
        except Unreadable:
            return None
        return os.path.normpath(found[0]) if len(found) == 1 else None

    def _gh(self, program: str, args: list):
        positional = _positional(args, GH_VALUED)
        if positional[:2] in (["repo", "clone"], ["gist", "clone"]) and len(positional) > 2:
            name = re.sub(r"\.git$", "", positional[2].rstrip("/").rsplit("/", 1)[-1].rsplit(":", 1)[-1])
            self.check([positional[3] if len(positional) > 3 else name])
            return
        if any(positional[:len(w)] == w for w in GH_WRITES_FILES):
            given = [args[i + 1] for i, w in enumerate(args[:-1]) if w in ("-D", "--dir")]
            self.into(given[0] if given else None)

    def _unpack(self, program: str, args: list):
        if program in ("tar", "bsdtar"):
            first = args[0] if args else ""
            modes = first if not first.startswith("-") else "".join(w[1:] for w in args
                                                                  if w.startswith("-") and not w.startswith("--"))
            if not ("x" in modes or "--extract" in args or "--get" in args):
                self.check(args)
                return
        given = [args[i + 1] for i, w in enumerate(args[:-1]) if w in ("-C", "-d", "--directory")]
        given += [w.split("=", 1)[1] for w in args if w.startswith("--directory=")]
        if not self.check(args):
            self.into(given[-1] if given else None)

    def _feed(self, args: list):
        """xargs and parallel run a program on paths read from stdin, which the hook does not see."""
        inner = next(iter(_positional(args, FEED_VALUED)), "")
        if os.path.basename(inner) in READS:
            return
        if not self.check(args):
            self.into(None)

    # -- merging, and the repo's own rules

    def github(self, words: list, redirections: list):
        at = 0
        while at < len(words) and (words[at] in PREFIXES or ASSIGNMENT.match(words[at])):
            at += 1
        if at == len(words):
            return
        program = os.path.basename(words[at])
        if program in READS:
            return
        if program not in ("git", "gh"):
            tool = next((i for i in range(at, len(words)) if os.path.basename(words[i]) in ("git", "gh")), None)
            unread = "a program names a merge, a setting or GitHub's API in a way the hook cannot read"
            if tool is None or program not in WRAPPERS:
                if (program in shell.SHELLS or program in shell.STRINGS) and shell.script_of(words, at) is not None:
                    return      # the script is read as commands of its own
                heredoc = INTERPRETERS.match(program) and any("<<" in op for op, _ in redirections)
                if _names_github(" ".join(words[at:]), self.data) or (heredoc and _names_github(self.text, self.data)):
                    self.ask("command_unreadable", unread)
                return
            # A wrapper runs the git or gh it names; but that word may be the value of one of its options, with what
            # it runs in text: `flock git -c '...'`. Its own words are read as text, and git's too.
            if _names_github(" ".join(words[at:tool] if os.path.basename(words[tool]) == "gh" else words[at:]),
                             self.data):
                self.ask("command_unreadable", unread)
            at = tool
        program, args = os.path.basename(words[at]), words[at + 1:]
        if program == "git":
            assigned = [w for w in words[:at] if ASSIGNMENT.match(w)]
            self._refs(args, assigned)
            self._push(args, assigned)
            return
        positional = _positional(args, GH_VALUED)
        if not positional:
            return
        if positional[0] not in GH_COMMANDS:
            self.ask("command_unreadable", "gh is given a command the hook does not know; it may be an alias or an "
                                           "extension")
            return
        if positional[:2] in (["alias", "set"], ["alias", "import"]):
            self.ask("command_unreadable", "gh alias makes a command the hook cannot read")
            return
        if positional[0] == "api":
            self.found += _api(args[args.index("api") + 1:], self.data, self.rules)
            return
        for group, code, does in (("merging", "merge", "merges a pull request around the queue"),
                                  ("settings", "repo_settings", "writes the repo's rules or settings")):
            for entry in self.data[group]["commands"]:
                if _is_command(entry, positional, args) and not any(
                        _is_command(read, positional, args) for read in self.data[group].get("reads", [])):
                    self.ask(code, "gh %s %s" % (entry, does))

    def _push(self, args: list, assigned: list = ()):
        here, i, elsewhere = self.here, 0, False
        while i < len(args) and args[i].startswith("-"):
            option, given, value = args[i].partition("=")
            if option in GIT_VALUED and not given:
                i += 1
                value = args[i] if i < len(args) else ""
            if option == "-C":
                here = self.cd_from(value, here)
            elsewhere = elsewhere or option in ("--git-dir", "--work-tree")
            i += 1
        if args[i:i + 1] != ["push"]:
            return
        if elsewhere or any(w.startswith(("GIT_DIR=", "GIT_WORK_TREE=")) for w in assigned):
            self.ask("merge", "the push is made from a repository the hook does not read, and may write %s"
                     % self.data["branch"])
            return
        if not os.path.isabs(here or ""):
            here = None
        rest, positional, j = args[i + 1:], [], 0
        while j < len(rest):
            option, given, _ = rest[j].partition("=")
            if rest[j] == "--":
                positional += rest[j + 1:]
                break
            if option in PUSH_VALUED and not given:
                j += 1
            elif not rest[j].startswith("-"):
                positional.append(rest[j])
            j += 1
        branch = self.data["branch"]
        if {"--all", "--mirror", "--branches"} & set(rest):
            self.ask("merge", "git push of every branch writes %s, which only a merge from the queue writes" % branch)
            return
        if not positional[1:] and not self._destination_read(here):
            return
        targets = []
        for spec in positional[1:] or ["HEAD"]:
            target = spec.lstrip("+").rsplit(":", 1)[-1]
            if spec in (":", "+:") or "*" in target:
                self.ask("merge", "a refspec with a wildcard, or the matching refspec, may write %s" % branch)
                return
            if target.startswith(REMOTE_REF):
                self.ask("remote_ref", "git push writes a ref under refs/remotes/, which a stop compares the "
                                       "branch with")
                return
            if target in ("HEAD", "@") or "$" in target or "`" in target:   # the branch it is on
                target = _branch(here, self.rules.root, self.env, self.spend)
                if target is None:
                    self.ask("merge", "the branch a push goes to cannot be read, and it may be %s" % branch)
                    return
            targets.append(target)
        if any(re.sub(r"^refs/heads/", "", t.casefold()) == branch.casefold() for t in targets):
            self.ask("merge", "git push writes %s, which only a merge from the queue writes" % branch)

    def _destination_read(self, here) -> bool:
        """Whether a push that names no refspec goes, exactly, to the branch it is on. If not, it asks."""
        branch = self.data["branch"]
        try:
            inside = self.rules.inside(here)      # git is run only in the project
            default = _git_config(inside, self.env, ["--get", "push.default"], self.spend)
            refspecs = _git_config(inside, self.env, ["--get-regexp", r"^remote\..*\.push$"], self.spend)
            mirrors = _git_config(inside, self.env, ["--type=bool", "--get-regexp", r"^remote\..*\.mirror$"],
                                  self.spend)
        except Unreadable:
            self.ask("merge", "a push that names no branch goes where git's configuration says, which the hook cannot "
                              "read, and it may be %s" % branch)
            return False
        if (default.strip().casefold() or None) not in PUSH_DEFAULTS or refspecs.strip() or any(
                line.endswith(" true") for line in mirrors.splitlines()):
            self.ask("merge", "a push that names no branch goes where push.default, remote.*.push or remote.*.mirror "
                              "says, which may be %s" % branch)
            return False
        return True

    def _refs(self, args: list, assigned: list = ()):
        """Ask about git that writes a ref under refs/remotes/, or the configuration that says where a push goes, and
        about git given a helper in the command, a program it runs that the hook does not read."""
        i, branch, fetched = 0, self.data["branch"], []     # fetched: refspecs given in the command, None if unread
        # The environment the command sets: on git itself, or earlier in the command (`export GIT_PAGER=...; git log`).
        environ = dict(w.split("=", 1) for w in assigned)
        environ.update({name: self.known.get(name) for name in self.assigned if name not in environ})
        named = set(environ)
        helper = any(GIT_HELPER_ENV_LOADS.match(name) or (GIT_HELPER_ENV.match(name) and (
            value is None or not self._reads_only(value, named))) for name, value in environ.items())
        while i < len(args) and args[i].startswith("-"):
            option, given, value = args[i].partition("=")
            if option in GIT_VALUED and not given:
                i += 1
                value = args[i] if i < len(args) else ""
            if option in ("-c", "--config-env") and PUSH_KEYS.match(value.split("=", 1)[0]):
                self.ask("merge", "git -c sets where a push goes, which may be %s" % branch)
            if option in ("-c", "--config-env") and value.casefold().startswith("alias."):
                self.ask("command_unreadable", "git -c defines an alias, a command the hook cannot read")
            if option in ("-c", "--config-env"):     # --config-env's setting is in the environment, unread
                helper = helper or self._configures_helper(value, option == "--config-env", named)
                key, _, setting = value.partition("=")
                if FETCH_KEYS.match(key.strip()):
                    fetched.append(setting if option == "-c" else None)
            helper = helper or (option == "--exec-path" and bool(given))
            i += 1
        sub, rest = (args[i], args[i + 1:]) if i < len(args) else ("", [])
        names = [w for w in rest if not w.startswith("-")]
        if sub and sub not in GIT_KNOWN:
            self.ask("command_unreadable", "git is given a command the hook does not know; it may be an alias")
            return
        # A remote helper's URL runs git-remote-<transport>, or for ext:: the command it names. A word in a variable is
        # read from what an earlier command set it to (URL=ext::x; git fetch "$URL").
        helper = helper or identity.remote_helper(sub, [self.expand(w) or w for w in args],
                                                  [self.expand(w) or w for w in rest])
        if sub in ("fetch", "pull"):
            # A refspec in a variable is read from what the command set it to; one the hook cannot read asks.
            fetched += [spec if spec is None or not ("$" in spec or "`" in spec) else self.expand(spec)
                        for spec in self._refspecs(rest)]
        no_ref = sub in ("fetch", "pull") and self._writes_no_ref(rest)     # it writes no local or remote ref
        if no_ref:
            fetched = []
        if any(spec is None or _moves_local_branch(spec) for spec in fetched):
            self.ask("local_branch", "git fetch moves a local branch, or reads where it goes from where the hook "
                                     "cannot, and it may be %s" % branch)
        for kind, value in identity.programs_given(sub, rest):
            helper = helper or kind == "always" or (kind == "program" and (
                value is None or not self._reads_only(value, named))) or (
                kind == "config" and self._configures_helper(value, False, named))
        if helper:
            self.ask("command_unreadable", "git is given a helper in the command, a program it runs that the hook "
                                           "does not read")
        if sub == "remote" and names[:1] and names[0] in ("add", "rename", "remove", "rm", "set-url", "set-branches"):
            self.ask("merge", "git remote changes where a push goes, which may be %s" % branch)
        if sub == "update-ref" and any(REMOTE_REF in w or w == "--stdin" for w in rest):
            self.ask("remote_ref", "git update-ref writes a ref under refs/remotes/, which a stop compares the branch with")
        elif sub == "fetch" and not no_ref and len(names) > 1 and not all(_own_branch(names[0], spec) for spec in [
                self.expand(w) or w if ("$" in w or "`" in w) else w for w in names[1:]]):    # S=a:b; fetch o "$S"
            self.ask("remote_ref", "git fetch writes a ref under refs/remotes/ from what is not that remote's branch "
                                   "of the same name, and a stop compares the branch with it")
        elif sub == "branch" and _deletes_remote(rest) and any(n.casefold().startswith("origin/") for n in names):
            self.ask("remote_ref", "git branch deletes a ref under refs/remotes/, which a stop compares the branch with")
        elif sub in ("branch", "tag") and not REF_READS & {w.split("=", 1)[0] for w in rest}:
            if sub == "branch" and any(w in ("-u", "--set-upstream-to") or w.startswith("--set-upstream-to=")
                                       for w in rest):
                self.ask("merge", "git branch sets where a push goes, which may be %s" % branch)
            elif any(n.startswith("origin/") or n.startswith("refs/") for n in names):
                self.ask("remote_ref", "git %s makes a name like a remote branch, which a stop compares the branch "
                                       "with" % sub)
        elif sub == "symbolic-ref" and (len(names) > 1 or "-d" in rest or "--delete" in rest):
            self.ask("remote_ref", "git symbolic-ref writes a ref, which a stop may compare the branch with")
        elif sub == "config":
            reads = {"--get", "--get-all", "--get-regexp", "--get-urlmatch", "-l", "--list", "get", "list"}
            if not reads & set(rest) and (len(names) > 1 or any(w.startswith("--unset") or w in ("--add", "unset",
                                          "--remove-section", "--rename-section", "--replace-all") for w in rest)):
                if any(PUSH_KEYS.match(n) or n.split(".")[0].casefold() in ("remote", "branch", "push")
                       for n in names if n not in ("set", "unset")):
                    self.ask("merge", "git config writes where a push goes, which may be %s" % branch)

    @staticmethod
    def _refspecs(rest: list) -> list:
        """The refspecs a fetch or a pull is given: each word after the repository that is neither an option nor an
        option's value, and --refmap's, spelt whole or by a prefix no other option shares. None for those read from
        stdin."""
        found, positional, k = [], [], 0
        while k < len(rest):
            word = rest[k]
            option, given, value = word.partition("=")
            if word == "--":
                positional += rest[k + 1:]
                break
            if word[:2] == "--":
                if _spelt(option, "--refmap") and len(option) >= len(FETCH_REFMAP):
                    if not given:
                        k += 1
                        value = rest[k] if k < len(rest) else ""
                    found.append(value)
                elif _spelt(option, "--stdin") and len(option) >= len(FETCH_STDIN):
                    found.append(None)
                elif not given and any(_spelt(option, name) for name in FETCH_VALUED):
                    k += 1      # its value: --shallow-since "2024-01-01 10:00"
            elif word[:1] == "-" and len(word) > 1:
                # -o a:b: the value is the next word; -oa:b holds it, and so does -rmerges, whatever letters follow.
                k += identity.takes_next(word, FETCH_SHORT_VALUED, FETCH_SHORT_OPTIONAL)
            else:
                positional.append(word)
            k += 1
        return found + positional[1:]

    @staticmethod
    def _writes_no_ref(rest: list) -> bool:
        """Whether a fetch's options say it writes no ref: --dry-run writes none, --prefetch none but under
        refs/prefetch/. The last of --dry-run/--no-dry-run (and of --prefetch/--no-prefetch) wins, and a word that
        is the value of an option (-o, --server-option, …) is not read as one, so the option parser skips it."""
        dry = pre = False
        k = 0
        while k < len(rest) and rest[k] != "--":
            word = rest[k]
            option = word.partition("=")[0]
            if word[:2] == "--":
                if "=" not in word and any(_spelt(option, name) for name in FETCH_VALUED):
                    k += 1      # its value is the next word, not an option: --server-option --dry-run
                elif _spelt(option, "--dry-run") and len(option) >= len("--dr"):
                    dry = True
                elif _spelt(option, "--prefetch") and len(option) >= len("--pre"):
                    pre = True
                elif _spelt(option, "--no-dry-run"):
                    dry = False
                elif _spelt(option, "--no-prefetch"):
                    pre = False
            elif word[:1] == "-" and len(word) > 1:
                k += identity.takes_next(word, FETCH_SHORT_VALUED, FETCH_SHORT_OPTIONAL)
            k += 1
        return dry or pre

    def _configures_helper(self, setting: str, unread: bool, named: set) -> bool:
        """Whether `key=value` given to git -c names a helper: one that loads code from a place, or a program that is
        not a reader. submodule.*.update names one only for a !cmd value, and a key set to nothing names none. With
        `unread`, the value is not in the command, and any helper key names a helper."""
        key, eq, value = setting.partition("=")
        key = key.strip()
        if GIT_HELPER_LOADS.match(key):
            return True
        if not GIT_HELPER_KEYS.match(key):
            return False
        if unread:
            return True
        return identity.names_program(key, bool(eq), value) and not self._reads_only(value, named)

    def _reads_only(self, program: str, named: set = frozenset()) -> bool:
        """Whether a helper git is given only reads: none, or `cat` or `less`, by their bare names, with no redirection,
        less with no option that writes or loads. `named` is what the command sets in the environment: with PATH, a
        bare name may be any program; with any of less's own, less may run or load one."""
        try:
            found = shell.commands(program, self.spend)
        except (ValueError, RecursionError):
            return False
        for words, targets in found:
            if targets or not words or words[0] not in HELPER_READERS:
                return False
            if "PATH" in named or words[0] == "less" and (any(n.startswith("LESS") for n in named)
                                                           or any(_less_writes(w) for w in words[1:])):
                return False
        return True


def _less_writes(word: str) -> bool:
    """Whether a word given to less makes it write a file or run or load commands: +, -o, -O or -k, alone or
    bundled, or a long option that writes a log or loads keys, by any prefix and in either case."""
    option = word.partition("=")[0].casefold()
    return bool(LESS_WRITES.match(word)) or option.startswith("--lesskey") or (
        word[:2] == "--" and any(_spelt(option, name) for name in LESS_WRITES_LONG))


# git branch's options that take the next word as their value.
BRANCH_VALUED = {"-u", "--set-upstream-to", "--sort", "--format", "--contains", "--no-contains", "--merged",
                 "--no-merged", "--points-at"}


_spelt = shell.spelt


def _deletes_remote(rest: list) -> bool:
    """Whether git branch's words delete remote branches: -r and -d or -D, alone, together (-rd) or spelt long, as
    git takes a long option by any prefix that is its own. The value of an option that takes one is not read."""
    flags, i = [], 0
    while i < len(rest) and rest[i] != "--":
        word = rest[i]
        if word.startswith("-") and "=" not in word and any(_spelt(word, v) for v in BRANCH_VALUED):
            i += 1      # its value, which may start with -: --sort -committerdate
        elif word.startswith("-"):
            flags.append(word.split("=", 1)[0])
        i += 1
    shorts = "".join(w[1:] for w in flags if not w.startswith("--"))
    longs = [w for w in flags if w.startswith("--") and len(w) > 2]
    return (("r" in shorts or any(_spelt(w, "--remotes") for w in longs))
            and ("d" in shorts or "D" in shorts or any(_spelt(w, "--delete") for w in longs)))


def _destination(spec: str):
    """The ref a fetch refspec writes, named as git names it (`main` is refs/heads/main, `remotes/x` refs/remotes/x),
    or None when it writes none. git reads the refs/, heads/, tags/ and remotes/ prefixes case-sensitively, so
    `main:Refs/tags/v1` makes the branch refs/heads/Refs/tags/v1."""
    if ":" not in spec or spec.startswith("^"):
        return None
    target = spec.lstrip("+").rsplit(":", 1)[1]
    if not target or target.startswith("refs/"):
        return target or None
    return "refs/" + target if target.startswith(("heads/", "tags/", "remotes/")) else LOCAL_REF + target


def _moves_local_branch(spec: str) -> bool:
    """Whether a fetch refspec writes a ref under refs/heads/, which moves a local branch."""
    target = _destination(spec)
    return target is not None and target.casefold().startswith(LOCAL_REF)


def _own_branch(repository: str, spec: str) -> bool:
    """Whether a fetch refspec writes, under refs/remotes/, only a named remote's own branch, by the same name."""
    target = _destination(spec)
    if target is None or not target.casefold().startswith(REMOTE_REF):
        return True
    source = spec.lstrip("+").rsplit(":", 1)[0]
    named = repository not in (".", "") and "/" not in repository and ":" not in repository
    return named and target == REMOTE_REF + repository + "/" + re.sub(r"^refs/heads/", "", source)


def _process_substitutions(text: str) -> tuple:
    """(text with each <( ... ) put as one word, the scripts inside them). Quoted text is left; one left open raises."""
    out, inner, i, quote = [], [], 0, None
    while i < len(text):
        c = text[i]
        if quote:
            if c == quote:
                quote = None
            elif c == "\\" and quote == '"':
                out.append(text[i:i + 2])
                i += 2
                continue
            out.append(c)
        elif c == "\\":
            out.append(text[i:i + 2])
            i += 2
            continue
        elif c in "'\"":
            quote = c
            out.append(c)
        elif text.startswith("<(", i):
            depth, j = 1, i + 2
            while j < len(text) and depth:
                depth += {"(": 1, ")": -1}.get(text[j], 0)
                j += 1
            if depth:
                raise ValueError("a process substitution is never closed")
            inner.append(text[i + 2:j - 1])
            out.append("/dev/fd/63")
            i = j
            continue
        else:
            out.append(c)
        i += 1
    return "".join(out), inner


HANDLED = {"sed", "find", "cp", "mv", "install", "git", "gh"}


def _branch(here, root: str, env: dict = None, spend=None):
    """The branch the tree at `here` is on, as git says: "" when HEAD is detached, None when it cannot be read.

    `here` is resolved and must lie in `root`, the project resolved, and so must the git directory git names for it.
    """
    here = _confined(here, root)
    if here is None or _git_dir(here, root, env, spend) is None:
        return None
    try:
        code, out = _run_git(here, env, ["symbolic-ref", "--quiet", "--short", "HEAD"], spend, system=False)
    except Unreadable:
        return None
    return out.strip() if code == 0 else "" if code == 1 else None


def _is_command(entry: str, positional: list, args: list) -> bool:
    """Whether gh's words are the command `entry` names, with every option it names."""
    words = entry.split()
    names = [w for w in words if not w.startswith("--")]
    options = [w for w in words if w.startswith("--")]
    return positional[:len(names)] == names and all(any(a == o or a.startswith(o + "=") for a in args) for o in options)


def _names_github(text: str, data: dict) -> bool:
    """Whether text names gh and then a merge or an API call, GitHub's API, or a GraphQL mutation that is the Maintainer's."""
    gh = GH_WORD.search(text)
    return bool((gh and GH_DOES.search(text, gh.end())) or _names_api(text)
                or _mutations(data["merging"]["mutations"] + data["settings"]["mutations"], text))


def _names_api(text: str) -> bool:
    """Whether text names GitHub's API, whose GraphQL endpoint is on the same host: a URL whose host is it, or the
    host named as a word outside any URL."""
    for url in URL.findall(text):
        try:
            host = (urlsplit(url).hostname or "").casefold().rstrip(".")      # api.github.com. is the same host
        except ValueError:      # a URL that cannot be read may name it
            return True
        if host == "api.github.com" or host.endswith(".api.github.com"):
            return True
    return bool(API_HOST.search(URL.sub(" ", text)))


def _git_dir(here, root: str, env: dict = None, spend=None):
    """The git directory of the tree at `here`, as git says, resolved; None when git cannot say, or it lies outside the
    project. Worktrees, and `.git` files, are git's to read."""
    here = _confined(here, root)
    if here is None:
        return None
    try:
        code, out = _run_git(here, env, ["rev-parse", "--absolute-git-dir"], spend, system=False)
    except Unreadable:
        return None
    return _confined(out.strip(), root) if code == 0 else None


def _confined(path, root: str):
    """`path` resolved, when it lies in `root`; None otherwise. What is outside the project is not read."""
    if not isinstance(path, str) or not os.path.isabs(path):
        return None
    real = os.path.realpath(path)
    return real if os.path.commonpath([root, real]) == root else None


def _wildcards(path: str, rules, limit: int = MATCHES) -> list:
    """The paths a pattern matches in the project's file system; the pattern itself when none does, as the shell
    leaves it. A directory outside the project is not listed."""
    spend = rules.spend
    parts, found = path.split("/"), ["/"]
    for part in parts[1:]:
        if not part:
            continue
        if not GLOB.search(part):
            found = [os.path.join(f, part) for f in found]
            continue
        if len(part) > 4 * NAME:
            raise Unreadable("a wildcard is longer than the hook reads")
        tokens, nxt = _tokens(part), []
        for f in found:
            real = rules.inside(f)
            if real is None:
                continue
            try:
                names = sorted(os.listdir(real))
            except OSError:
                continue
            for n in names:
                spend()     # each name costs at most len(part) times len(n) steps
                if _match(tokens, n):
                    nxt.append(os.path.join(f, n))
            if len(nxt) > limit:
                raise Unreadable("a wildcard matches more paths than the hook reads")
        found = nxt
    return found or [path]


def _tokens(pattern: str) -> list:
    """A shell pattern for one name as tokens: "*", "?", a class (negated, set of ranges), or one character."""
    out, i = [], 0
    while i < len(pattern):
        c = pattern[i]
        end = pattern.find("]", i + 2) if c == "[" else -1
        if c in "*?":
            if not (c == "*" and out and out[-1] == "*"):
                out.append(c)
        elif end > 0:
            body = pattern[i + 1:end]
            negated = body[:1] in ("!", "^")
            body = body[1:] if negated else body
            ranges, j = [], 0
            while j < len(body):
                if j + 2 < len(body) and body[j + 1] == "-":
                    ranges.append((body[j].casefold(), body[j + 2].casefold()))
                    j += 3
                else:
                    ranges.append((body[j].casefold(), body[j].casefold()))
                    j += 1
            out.append((negated, ranges))
            i = end
        else:
            out.append(c.casefold())
        i += 1
    return out


def _one(token, c: str) -> bool:
    if token == "?":
        return True
    if isinstance(token, tuple):
        negated, ranges = token
        return any(low <= c <= high for low, high in ranges) != negated
    return token == c


def _glob_match(pattern: str, name: str) -> bool:
    """Whether a shell pattern matches one name, without regard to case."""
    return _match(_tokens(pattern), name)


def _match(tokens: list, name: str) -> bool:
    """Whether tokens of a pattern match one name. Two pointers, going back only to the last star: at most
    len(tokens) times len(name) steps, never more."""
    name = name.casefold()
    p = n = 0
    star, mark = -1, 0
    while n < len(name):
        if p < len(tokens) and tokens[p] != "*" and _one(tokens[p], name[n]):
            p, n = p + 1, n + 1
        elif p < len(tokens) and tokens[p] == "*":
            star, mark, p = p, n, p + 1
        elif star >= 0:
            mark += 1
            p, n = star + 1, mark
        else:
            return False
    while p < len(tokens) and tokens[p] == "*":
        p += 1
    return p == len(tokens)


def _starred(word: str, spend) -> str:
    """The word with each brace expansion ({a,b} or {1..9}) made a wildcard, in one pass; braces left open stay."""
    out, open_at = [], []       # open_at: [where the brace starts in out, whether it expands]
    i = 0
    while i < len(word):
        if i % 4096 == 0:
            spend()
        c = word[i]
        if c == "{":
            open_at.append([len(out), False])
            out.append(c)
        elif c == "}" and open_at:
            start, expands = open_at.pop()
            if expands:
                del out[start:]     # each character is taken away at most once
                out.append("*")
                if open_at:
                    open_at[-1][1] = True
            else:
                out.append(c)
        elif c == "," and open_at:
            open_at[-1][1] = True
            out.append(c)
        elif c == "." and open_at and word.startswith("..", i):
            open_at[-1][1] = True
            out.append("..")
            i += 1
        else:
            out.append(c)
        i += 1
    return "".join(out)


def _run_git(here, env: dict, args: list, spend, system: bool = True) -> tuple:
    """(exit code, output) of git run in `here` with these arguments, never through a shell, within the hook's budget.
    Without `system`, git reads no system-wide configuration. Raises Unreadable when git cannot be run."""
    spend = spend or Budget(DEADLINE)
    env = dict(os.environ if env is None else env)
    spend()
    exe = shutil.which("git", path=env.get("PATH", os.defpath))
    if exe is None or not here:
        raise Unreadable("git cannot be run")
    if not system:
        env["GIT_CONFIG_NOSYSTEM"] = "1"
    try:
        done = subprocess.run([exe, "-C", here] + args, cwd=here, env=env, capture_output=True, text=True,
                              timeout=max(0.1, spend.left()))
    except (OSError, subprocess.TimeoutExpired):
        raise Unreadable("git cannot be run")
    return done.returncode, done.stdout


def _git_config(here, env: dict, args: list, spend) -> str:
    """What `git config` says in `here`: "" when the key is not set. Raises Unreadable when git cannot say."""
    try:
        code, out = _run_git(here, env, ["config"] + args, spend)
    except Unreadable:
        raise Unreadable("git's configuration cannot be read")
    if code not in (0, 1):
        raise Unreadable("git's configuration cannot be read")
    return out if code == 0 else ""


def _without_script(program: str, args: list) -> list:
    """An interpreter's words but the script file it runs, which it reads. Code given inline stays, to be read as text."""
    if re.match(r"^(awk|gawk|mawk|nawk)$", program):
        return args     # the first word is the program's text
    for at, word in enumerate(args):
        if word in CODE_FOLLOWS or (word.startswith("-") and not word.startswith("--") and "c" in word[1:]
                                    and program in shell.SHELLS):
            return args
        if not word.startswith("-"):
            return args[:at] + args[at + 1:]
    return args


def _positional(args: list, valued: set) -> list:
    out, i = [], 0
    while i < len(args):
        option, given, _ = args[i].partition("=")
        if option in valued and not given:
            i += 1
        elif not args[i].startswith("-"):
            out.append(args[i])
        i += 1
    return out


def _route(pattern: str, endpoint: str) -> bool:
    want, have = pattern.split("/"), endpoint.split("/")
    if want[-1] == "**":
        want = want[:-1]
        if len(have) < len(want):
            return False
    elif len(have) != len(want):
        return False
    return all(w == "*" or w == h for w, h in zip(want, have))


def _endpoint(raw: str):
    """A REST path as GitHub routes it: no host, no query, no . or .., decoded, lower case, a repository by its id read
    as one by its name. None if it cannot be read."""
    if "$" in raw or "`" in raw:
        return None
    path = re.sub(r"^[a-z]+://[^/]+/", "", raw.strip(), flags=re.I).split("?")[0].split("#")[0]
    for _ in range(3):
        path = re.sub(r"%([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), path)
    path = os.path.normpath("/" + path.lstrip("/")).lstrip("/").casefold()
    path = re.sub(r"^api/v3/", "", path)
    return re.sub(r"^repositories/[^/]+", "repos/-/-", path)


def _mutations(patterns: list, text: str) -> list:
    if "mutation" not in text.casefold():
        return []
    names = set(re.findall(r"[_a-z][_a-z0-9]*", text.casefold()))
    return [p for p in patterns if any(re.match(_glob(p.casefold(), "[_a-z0-9]") + r"\Z", n, re.S) for n in names)]


def _api(args: list, data: dict, rules: Rules) -> list:
    method, endpoint, values, fields, unread, unknown, i = None, None, [], {}, False, False, 0
    while i < len(args):
        word = args[i]
        option, given, value = word.partition("=")
        if not word.startswith("--") and len(word) > 2 and word[:2] in API_VALUED:
            option, given, value = word[:2], "=", word[2:]
        if word.startswith("-") and len(word) > 1:
            if option in API_VALUED:
                if not given:
                    i += 1
                    value = args[i] if i < len(args) else ""
                if option in ("-X", "--method"):
                    method = value.upper()
                elif option in ("-f", "--raw-field", "-F", "--field"):
                    name, _, field = value.partition("=")
                    fields[name] = field
                    values.append(field)
                    unread = unread or field[:1] in ("@", "$", "`")
                elif option == "--input":
                    values.append("")
                    unread = True
            elif option not in API_FLAGS:
                unknown = True
        elif endpoint is None:
            endpoint = word
        i += 1
    if endpoint is None:
        return []
    method = method or ("POST" if values else "GET")
    path = _endpoint(endpoint)
    found = []
    if path == "graphql":
        text = " ".join(values)
        for group, code in (("merging", "merge"), ("settings", "repo_settings")):
            for name in _mutations(data[group]["mutations"], text):
                found.append((code, "the GraphQL mutation %s is the Maintainer's" % name))
        if unread and not found:
            found.append(("command_unreadable", "gh api graphql reads its query from a file, stdin or a variable, so "
                                                "what it changes cannot be read"))
        return found
    if method in ("GET", "HEAD"):
        return []
    if path is None:
        return [("command_unreadable", "gh api writes to an endpoint the hook cannot read")]
    for pattern in data["merging"]["endpoints"]:
        if _route(pattern, path):
            found.append(("merge", "gh api writes %s, which merges or moves a branch" % pattern))
    for pattern in data["settings"]["endpoints"]:
        if _route(pattern, path):
            found.append(("repo_settings", "gh api writes %s, the repo's rules or settings" % pattern))
    contents = re.match(r"repos/[^/]+/[^/]+/contents/", path)
    target = fields.get("branch")
    if contents and method in ("PUT", "DELETE") and (unread or target is None or "$" in target or "`" in target
                                                     or re.sub(r"^refs/heads/", "", target) == data["branch"]):
        found.append(("merge", "gh api writes through the contents API to %s, or to a branch it cannot read"
                      % data["branch"]))
    named = rules.names(path.split("/", 4)[4]) if contents else None
    if named:
        found.append(("protected_path", "gh api writes %s on GitHub, which is %s" % named))
    if not found and unknown:
        found.append(("command_unreadable", "gh api is given an option the hook does not know"))
    return found


# ---- the hook

def check(payload: dict, env: dict, data: dict = None, source: pathlib.Path = ROOT / "config" / "hooks.json",
          seconds: float = DEADLINE) -> list:
    """The reasons to ask the person about this tool call, as (code, sentence); none when it is not the Maintainer's."""
    tool = payload.get("tool_name")
    if tool not in FILE_TOOLS and tool != "Bash":
        return []
    try:
        data = data or load(source)
    except Unreadable as err:
        return [("config_unreadable", "%s, so every edit and command is asked about" % err)]
    try:
        rules = Rules(data, env, Budget(seconds))
        if tool in FILE_TOOLS:
            return edit(payload, rules)
        command = (payload.get("tool_input") or {}).get("command")
        if not isinstance(command, str):
            return [("command_unreadable", "the Bash call carries no command")]
        return list(dict.fromkeys(Command(command, payload.get("cwd"), rules, data, env).read()))
    except Spent:
        return [("budget_spent", "the hook ran out of its %d seconds reading this, so it asks" % seconds)]


def respond(payload: dict, env: dict) -> str:
    """What the hook prints: a decision to ask, with its reasons, or nothing."""
    try:
        found = check(payload, env)
    except Exception as err:    # what the hook cannot read, it asks about
        found = [("hook_failed", "the hook could not finish (%s), so it asks" % type(err).__name__)]
    if not found:
        return ""
    # A sentence holds codes, text from config/hooks.json and the hook's own words: never a word of the command.
    reasons = ["%s: %s." % (code, sentence) for code, sentence in found[:SHOWN]]
    if len(found) > SHOWN:
        reasons.append("and %d more." % (len(found) - SHOWN))
    reason = ("Asked by tools/hooks/protected.py. This is the Maintainer's to decide (config/hooks.json): "
              + " ".join(reasons))
    return json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask",
                                              "permissionDecisionReason": reason}}) + "\n"


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
        if not isinstance(payload, dict):
            raise ValueError("not an object")
    except ValueError:
        payload = {"tool_name": "Bash", "tool_input": None}
    sys.stdout.write(respond(payload, dict(os.environ)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
