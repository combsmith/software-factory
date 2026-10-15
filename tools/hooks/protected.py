"""PreToolUse on an edit or a Bash command: what is the Maintainer's to decide is asked of the person.

Three things are (§5.1, §9.12): an edit to a protected path, one of the Factory's own rules or a
hook that holds them; merging a pull request, or adding one to the queue; and a write to a ruleset
or to the repo's settings. For each the hook answers "ask", and the person answers. That the
Maintainer asked is never inferred from the conversation. The hook allows nothing and refuses
nothing: what it does not ask about goes through the session's own permissions. What it cannot read
it asks about. The paths, the commands, the mutations and the endpoints are data, in
`config/hooks.json`.

A protected path is protected in every working tree: the project, a worktree under
`.claude/worktrees/`, or any other directory that holds a `.git`, since its branch can merge here.
A path is read as it is written, normalised, and as the file system resolves it, symbolic links
followed, and compared without regard to case. Run as `python3 -I` on this file; see after_edit.py.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT))
from tools.hooks import shell  # noqa: E402

FILE_TOOLS = {"Edit": "file_path", "Write": "file_path", "MultiEdit": "file_path", "NotebookEdit": "notebook_path"}
SHOWN = 6           # reasons put in front of the person
GLOB = re.compile(r"[*?\[]")
VARIABLE = re.compile(r"\$(?:\{([A-Za-z_]\w*)\}|([A-Za-z_]\w*))")
ASSIGNMENT = re.compile(r"^[A-Za-z_]\w*=")
# Words that come before the program and change nothing about what it does.
PREFIXES = {"if", "then", "else", "elif", "do", "while", "until", "!", "{", "}", "time", "command", "builtin", "exec",
            "nohup"}
# Programs that read the paths they are named and write none of them. A redirection is read apart from them.
READS = {"cat", "less", "more", "head", "tail", "wc", "grep", "egrep", "fgrep", "rg", "ls", "stat", "file", "diff",
         "cmp", "readlink", "realpath", "basename", "dirname", "test", "[", "[[", "echo", "printf", "true", "false",
         "jq", "nl", "od", "hexdump", "md5", "md5sum", "shasum", "sha1sum", "sha256sum", "cksum", "du", "cut", "tr",
         "comm", "paste", "column", "fold", "strings", "which", "type", "pwd", "sleep", "export", "unset", "set",
         "local", "declare", "readonly", "read", "shift", "exit", "return", "wait", "case", "esac", "fi", "done",
         "cd", "pushd", "popd"}
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
GIT_VALUED = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env"}
PUSH_VALUED = {"-o", "--push-option", "--receive-pack", "--exec", "--repo"}
GH_VALUED = {"-R", "--repo", "--hostname"}
GH_COMMANDS = {"accessibility", "agent-task", "alias", "api", "attestation", "auth", "browse", "cache", "co",
               "codespace", "completion", "config", "copilot", "extension", "ext", "gist", "gpg-key", "help", "issue",
               "label", "org", "pr", "preview", "project", "release", "repo", "ruleset", "run", "search", "secret",
               "ssh-key", "status", "variable", "version", "workflow"}
GH_WRITES_FILES = (["run", "download"], ["release", "download"], ["repo", "clone"], ["gist", "clone"])
API_VALUED = {"-X", "--method", "-H", "--header", "-f", "--raw-field", "-F", "--field", "--input", "-q", "--jq",
              "-t", "--template", "--cache", "-p", "--preview", "--hostname"}
API_FLAGS = {"-i", "--include", "--paginate", "--slurp", "--silent", "--verbose"}
# Text that names a merge or GitHub's API in a program the hook cannot read as gh.
GITHUB_TEXT = re.compile(r"\bgh\b[\s\S]*\b(merge|api|ruleset|repo|secret|variable|workflow|alias)\b|"
                         r"api\.github\.com|github\.com/graphql", re.I)


class Unreadable(Exception):
    """What the decision rests on could not be read."""


def _glob(pattern: str, segment: str) -> str:
    """A regular expression for a pattern of names: `*` is any part of one name (`segment` is what a name is made of)."""
    return "".join(segment + "*" if c == "*" else re.escape(c) for c in pattern)


def load(path: pathlib.Path = ROOT / "config" / "hooks.json") -> dict:
    """The data the hook asks from. Raises Unreadable when it is missing or has not the shape the hook reads."""
    try:
        data = json.loads(path.read_text())
        protected = [(e["path"], e["is"]) for e in data["protected"]]
        lists = {group: {key: list(data[group][key]) for key in ("commands", "mutations", "endpoints")}
                 for group in ("merging", "settings")}
        branch = data["merging"]["branch"]
    except (OSError, ValueError, KeyError, TypeError) as err:
        raise Unreadable("config/hooks.json cannot be read (%s)" % type(err).__name__)
    words = [p for p, _ in protected] + [branch] + [w for group in lists.values() for v in group.values() for w in v]
    if not protected or not all(isinstance(w, str) and w for w in words) or any(".." in p.split("/") for p, _ in protected):
        raise Unreadable("config/hooks.json does not have the shape the hook reads")
    return {"protected": protected, "branch": branch, **lists}


class Rules:
    """The protected paths, and where to read them from: the top of every working tree that holds a path."""

    def __init__(self, data: dict, env: dict):
        self.entries, self.named = [], []
        for path, what in data["protected"]:
            parts = path.casefold().rstrip("/").split("/")
            whole = re.compile("/".join(_glob(p, "[^/]") for p in parts) + ("(/.*)?" if path.endswith("/") else "")
                               + r"\Z")
            self.entries.append((path, what, parts, whole))
            # As text, a path is named whole, or a file by its own name: in a script, `open("authority.json")`.
            forms = ["/".join(parts)] + ([parts[-1]] if not path.endswith("/") and len(parts) > 1 else [])
            self.named.append((re.compile(r"(?<![\w.-])(%s)(?![\w.-])" % "|".join(
                _glob(f, r"[^/\s'\"]") for f in forms)), path, what))
        project = pathlib.Path(env.get("CLAUDE_PROJECT_DIR") or ROOT)
        tops = {str(project), str(ROOT)} | ({env["HOME"]} if env.get("HOME") else set())
        self.tops = {os.path.normpath(t) for t in tops} | {os.path.realpath(t) for t in tops}
        self.worktrees = {os.path.join(t, ".claude", "worktrees").casefold() for t in self.tops}

    def names(self, text: str):
        """The protected path that `text` names, as text, wherever it stands; None if none."""
        text = text.casefold().replace("\\", "")
        return next(((path, what) for named, path, what in self.named if named.search(text)), None)

    def _tops(self, path: str) -> set:
        found, here = set(self.tops), path
        while True:
            parent = os.path.dirname(here)
            if os.path.lexists(os.path.join(here, ".git")) or parent.casefold() in self.worktrees:
                found.add(here)
            if parent == here:
                return found
            here = parent

    def where(self, path: str, holds: bool = True):
        """(path in config, what it is) for an absolute path that is protected, or that holds one; None otherwise.

        `holds` counts a directory that holds a protected path, which a command that writes below it can reach.
        """
        for form in dict.fromkeys((os.path.normpath(path), os.path.realpath(path))):
            low = form.casefold()
            for top in self._tops(form):
                top = top.casefold()
                if low == top or (top.startswith(low.rstrip("/") + "/") and holds):
                    if holds:
                        return "a working tree", "a directory that holds every protected path"
                    continue
                if not low.startswith(top.rstrip("/") + "/"):
                    continue
                rel = low[len(top.rstrip("/")) + 1:]
                parts = rel.split("/")
                for path_, what, entry, whole in self.entries:
                    if whole.match(rel):
                        return path_, what
                    if holds and len(parts) < len(entry) and all(
                            re.match(_glob(e, "[^/]") + r"\Z", p) for e, p in zip(entry, parts)):
                        return path_, "a directory that holds %s" % what
        return None


def _hard_linked(path: str) -> bool:
    try:
        st = os.stat(path)
    except OSError:
        return False
    return st.st_nlink > 1 and not os.path.isdir(path)


# ---- the file tools

def edit(payload: dict, rules: Rules) -> list:
    key = FILE_TOOLS[payload["tool_name"]]
    path = (payload.get("tool_input") or {}).get(key)
    if not isinstance(path, str) or not path:
        return [("path_unreadable", "the %s names no %s" % (payload["tool_name"], key))]
    if not os.path.isabs(path):
        cwd = payload.get("cwd")
        if not cwd:
            return [("path_unreadable", "the %s names a relative path, and the session's directory is not given"
                     % payload["tool_name"])]
        path = os.path.join(cwd, path)
    found = rules.where(path, holds=False)
    if found:
        return [("protected_path", "%s is %s" % found)]
    if _hard_linked(path):
        return [("path_unreadable", "the file has more than one name, and one may be protected")]
    return []


# ---- Bash: the paths a command writes

class Command:
    """One Bash command read for the paths it writes, simple command by simple command."""

    def __init__(self, text: str, cwd, rules: Rules, env: dict):
        self.text, self.rules = text, rules
        self.here = os.path.normpath(cwd) if cwd and os.path.isabs(cwd) else None
        self.known = {k: env[k] for k in ("HOME", "TMPDIR", "CLAUDE_PROJECT_DIR") if env.get(k)}
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
        """The absolute paths a word may name, braces and wildcards expanded as the shell would. Raises Unreadable."""
        here = here or self.here
        word = self.expand(word)
        if word is None:
            raise Unreadable("a path is held in a variable or a command the hook cannot read")
        out = []
        for one in _braces(word):
            if not os.path.isabs(one):
                if here is None:
                    raise Unreadable("the directory the command runs in cannot be told from its words")
                one = os.path.join(here, one)
            out += _wildcards(one) if GLOB.search(one) else [one]
        return out

    def hit(self, word: str, holds: bool = True, here=None, text: bool = True):
        """What protected path a word names, by where it leads or, with `text`, as text; None if none.

        Raises Unreadable when where it leads cannot be read.
        """
        named = self.rules.names(word) if text else None
        if named:
            return named
        for value in [word] + ([word.split("=", 1)[1]] if "=" in word[1:] else []):
            if value.startswith("-") or not value:
                continue
            for path in self.paths(value, here):
                found = self.rules.where(path, holds)
                if found:
                    return found
                if _hard_linked(path):
                    return "a file with more than one name", "one of them may be protected"
        return None

    def check(self, program: str, words: list, holds: bool = True, here=None, text: bool = True) -> bool:
        """Ask about the first word of a program that writes what its words name. Whether it asked."""
        for word in words:
            try:
                found = self.hit(word, holds, here, text)
            except Unreadable as err:
                self.ask("path_unreadable", "%s is given a path the hook cannot read: %s" % (_shown(program), err))
                return True
            if found:
                self.ask("protected_path", "%s may write %s, which is %s" % (_shown(program), found[0], found[1]))
                return True
        return False

    def into(self, program: str, where, here=None) -> bool:
        """Ask if a program writes files it does not name into `where`, or where it runs, and that holds a protected path."""
        here = here or self.here
        try:
            places = self.paths(where, here) if where else ([here] if here else None)
        except Unreadable:
            places = None
        if not places:
            self.ask("path_unreadable", "%s writes into a directory the hook cannot read" % _shown(program))
            return True
        for place in places:
            found = self.rules.where(place)
            if found:
                self.ask("protected_path", "%s writes files it does not name into %s, which is %s"
                         % ((_shown(program),) + found))
                return True
        return False

    # -- the command

    def read(self) -> list:
        if ">(" in self.text:
            self.ask("command_unreadable", "a process substitution writes where the hook cannot follow")
        try:
            commands = shell.commands(self.text)
        except ValueError as err:
            self.ask("command_unreadable", "the command cannot be split into words (%s)" % err)
            return self.found
        for at, (words, redirections) in enumerate(commands):
            if words and words[-1].endswith("=$") and at + 1 < len(commands):
                # Unquoted, D=$(mktemp -d) is read as D=$ and the command inside: put them together again.
                words = words[:-1] + [words[-1] + "(%s)" % " ".join(commands[at + 1][0])]
            self.redirections(words, redirections)
            if words:
                self.simple(words, redirections)
        return self.found

    def redirections(self, words: list, redirections: list):
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

    def simple(self, words: list, redirections: list):
        at = 0
        while at < len(words) and (words[at] in PREFIXES or ASSIGNMENT.match(words[at])):
            if ASSIGNMENT.match(words[at]):
                self.assign(words[at])
            at += 1
        if at == len(words):
            return
        program, args = os.path.basename(words[at]), words[at + 1:]
        if program in ("cd", "pushd", "popd"):
            self.here = None if program == "popd" or (args and args[0] == "-") else self.cd(args[0] if args else "~")
            return
        if program in ("export", "local", "declare", "readonly"):
            for word in args:
                if ASSIGNMENT.match(word):
                    self.assign(word)
            return
        if program in READS:
            return
        if program in shell.SHELLS and any(w.startswith("-") and not w.startswith("--") and "c" in w for w in args):
            return      # the script it runs is read as commands of its own
        if program == "eval":
            return
        if INTERPRETERS.match(program):
            if any("<<" in op and "<<<" not in op for op, _ in redirections):
                found = self.rules.names(self.text)
                if found:
                    self.ask("protected_path", "%s runs a script that names %s, which is %s, and the hook cannot "
                                               "tell a read from a write" % ((_shown(program),) + found))
                    return
            args = _without_script(program, args)
        handler = getattr(self, "_" + program.replace("-", "_"), None) if program in HANDLED else None
        if handler:
            handler(program, args)
        elif program in UNPACKERS:
            self._unpack(program, args)
        elif program in FEEDERS:
            self._feed(program, args)
        else:
            self.check(program, args)

    def assign(self, word: str):
        name, value = word.split("=", 1)
        inner = re.match(r"^(?:\$\((.*)\)|`(.*)`)$", value, re.S)
        if inner and re.match(r"^mktemp(\s+(-d|-q|-u|-t\s+\S+))*\s*$", (inner.group(1) or inner.group(2)).strip()):
            self.known[name] = os.path.join(self.known.get("TMPDIR", "/tmp"), "mktemp")
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
            self.check(program, args)
            return
        for word in args:       # a script names what it writes as text; a file it reads leads somewhere
            named = self.rules.names(word)
            if named:
                try:
                    lead = any(self.rules.where(p, holds=False) for p in self.paths(word))
                except Unreadable:
                    lead = False
                if not lead:
                    self.ask("protected_path", "%s's script names %s, which is %s" % ((_shown(program),) + named))
                    return

    def _find(self, program: str, args: list):
        runs = [args[i + 1] for i, w in enumerate(args[:-1]) if w in FIND_RUNS]
        if FIND_WRITES & set(args) or any(os.path.basename(r) not in READS for r in runs):
            self.check(program, args)

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
        if program == "mv" and self.check(program, positional):
            return
        try:
            places = self.paths(target)
        except Unreadable as err:
            self.ask("path_unreadable", "%s is given a target the hook cannot read: %s" % (program, err))
            return
        for place in places:
            if as_file or not (os.path.isdir(place) or target.endswith("/")):
                if self.check(program, [place], holds=False):
                    return
                continue
            for source in positional:      # into a directory: each source by its own name
                name = os.path.basename(source.rstrip("/"))
                if source.endswith("/") or name in (".", ""):
                    into = place            # what is in the source, not the source itself
                elif self.expand(name) is None:
                    into = os.path.join(place, "*")     # a name the hook cannot read may be any name there
                else:
                    into = os.path.join(place, name)
                if self.check(program, [into]):
                    return

    _mv = _install = _cp

    def _git(self, program: str, args: list):
        here, i, tree_unknown = self.here, 0, False
        while i < len(args) and args[i].startswith("-"):
            option, given, value = args[i].partition("=")
            if option in GIT_VALUED and not given:
                i += 1
                value = args[i] if i < len(args) else ""
            if option == "-C":
                try:
                    found = self.paths(value, here)
                    here = os.path.normpath(found[0]) if len(found) == 1 else None
                except Unreadable:
                    here = None
            elif option in ("--git-dir", "--work-tree"):
                tree_unknown = True
            i += 1
        sub, rest = (args[i], args[i + 1:]) if i < len(args) else ("", [])
        sub, rest = (args[i], args[i + 1:]) if i < len(args) else ("", [])
        shown = "git " + _shown(sub)
        if sub in GIT_READS:        # but --output writes a file
            outputs = [rest[j + 1] if w == "--output" and j + 1 < len(rest) else w[len("--output="):]
                       for j, w in enumerate(rest) if w == "--output" or w.startswith("--output=")]
            self.check(shown, outputs, holds=False, here=here, text=False)
            return
        if tree_unknown:
            self.ask("path_unreadable", "%s is pointed at a working tree the hook does not read" % shown)
            return
        if sub in ("apply", "am") or (sub == "stash" and rest[:1] in (["pop"], ["apply"])):
            self.into(shown, None, here)        # what it writes is in a patch or a stash, which the hook does not read
            return
        if any(w.startswith(":") for w in rest):
            self.ask("path_unreadable", "%s is given a pathspec with magic the hook does not read" % shown)
            return
        # git matches a pathspec's wildcards across directories: read one as the directory it starts in.
        globbed = [w[:GLOB.search(w).start()].rpartition("/")[0] or "." for w in rest
                   if GLOB.search(w) and not w.startswith("-")]
        if not self.check(shown, globbed, here=here, text=False):
            self.check(shown, rest, here=here, text=False)

    def _gh(self, program: str, args: list):
        positional = _positional(args, GH_VALUED)
        if any(positional[:len(w)] == w for w in GH_WRITES_FILES):
            given = [args[i + 1] for i, w in enumerate(args[:-1]) if w in ("-D", "--dir")]
            self.into("gh " + " ".join(positional[:2]), given[0] if given else None)

    def _unpack(self, program: str, args: list):
        if program in ("tar", "bsdtar"):
            first = args[0] if args else ""
            modes = first if not first.startswith("-") else "".join(w[1:] for w in args
                                                                  if w.startswith("-") and not w.startswith("--"))
            if not ("x" in modes or "--extract" in args or "--get" in args):
                self.check(program, args)
                return
        given = [args[i + 1] for i, w in enumerate(args[:-1]) if w in ("-C", "-d", "--directory")]
        given += [w.split("=", 1)[1] for w in args if w.startswith("--directory=")]
        if not self.check(program, args):
            self.into(program, given[-1] if given else None)

    def _feed(self, program: str, args: list):
        """xargs and parallel run a program on paths read from stdin, which the hook does not see."""
        inner = next(iter(_positional(args, FEED_VALUED)), "")
        if os.path.basename(inner) in READS:
            return
        if not self.check(program, args):
            self.into("%s %s" % (program, _shown(os.path.basename(inner))), None)


HANDLED = {"sed", "find", "cp", "mv", "install", "git", "gh"}


def _braces(word: str) -> list:
    """The words a brace list `{a,b}` stands for, as the shell would expand it."""
    found = re.search(r"\{([^{}]*,[^{}]*)\}", word)
    if not found:
        return [word]
    out = []
    for part in found.group(1).split(","):
        out += _braces(word[:found.start()] + part + word[found.end():])
    return out


def _wildcards(path: str, limit: int = 2000) -> list:
    """The paths a pattern matches in the file system; the pattern itself when none does, as the shell leaves it."""
    parts, found = path.split("/"), ["/"]
    for part in parts[1:]:
        if not part:
            continue
        if not GLOB.search(part):
            found = [os.path.join(f, part) for f in found]
            continue
        pattern = re.compile(_shell_glob(part) + r"\Z", re.I)
        nxt = []
        for f in found:
            try:
                nxt += [os.path.join(f, n) for n in sorted(os.listdir(f)) if pattern.match(n)]
            except OSError:
                continue
        if len(nxt) > limit:
            raise Unreadable("a wildcard matches more paths than the hook reads")
        found = nxt
    return found or [path]


def _shell_glob(part: str) -> str:
    out, i = [], 0
    while i < len(part):
        c = part[i]
        if c == "*":
            out.append(".*")
        elif c == "?":
            out.append(".")
        elif c == "[":
            end = part.find("]", i + 2)
            if end < 0:
                out.append(re.escape(c))
            else:
                body = part[i + 1:end]
                out.append("[" + ("^" + body[1:] if body[:1] in "!^" and body else body).replace("\\", "\\\\") + "]")
                i = end
        else:
            out.append(re.escape(c))
        i += 1
    return "".join(out)


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


def _shown(word: str) -> str:
    """A program's name, cut short and with nothing in it that is not printable, to put in front of the person."""
    return re.sub(r"[^\w.+-]", "?", word)[:40]


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


# ---- Bash: merging, and the repo's own rules

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
    """A REST path as GitHub routes it: no host, no query, no . or .., decoded, lower case. None if it cannot be read."""
    if "$" in raw or "`" in raw:
        return None
    path = re.sub(r"^[a-z]+://[^/]+/", "", raw.strip(), flags=re.I).split("?")[0].split("#")[0]
    for _ in range(3):
        path = re.sub(r"%([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), path)
    path = os.path.normpath("/" + path.lstrip("/")).lstrip("/").casefold()
    return re.sub(r"^api/v3/", "", path)


def _mutations(patterns: list, text: str) -> list:
    if "mutation" not in text.casefold():
        return []
    names = set(re.findall(r"[_a-z][_a-z0-9]*", text.casefold()))
    return [p for p in patterns if any(re.match(_glob(p.casefold(), "[_a-z0-9]") + r"\Z", n) for n in names)]


def _api(args: list, data: dict, rules: Rules) -> list:
    method, endpoint, values, unread, i = None, None, [], [], 0
    while i < len(args):
        word = args[i]
        option, given, value = word.partition("=")
        short = word[:2] if not word.startswith("--") and len(word) > 2 and word[:2] in API_VALUED else None
        if short:
            option, given, value = short, "=", word[2:]
        if word.startswith("-") and len(word) > 1:
            if option in API_VALUED:
                if not given:
                    i += 1
                    value = args[i] if i < len(args) else ""
                if option in ("-X", "--method"):
                    method = value.upper()
                elif option in ("-f", "--raw-field", "-F", "--field"):
                    field = value.partition("=")[2]
                    values.append(field)
                    if field.startswith("@") or field.startswith("$") or field.startswith("`"):
                        unread.append("a field is read from a file, stdin or a variable")
                elif option == "--input":
                    values.append("")
                    unread.append("the body is read from a file or stdin")
            elif option not in API_FLAGS:
                unread.append("gh api %s is an option the hook does not know" % _shown(option))
        elif endpoint is None:
            endpoint = word
        i += 1
    if endpoint is None:
        return []
    method = method or ("POST" if values else "GET")
    writes = method not in ("GET", "HEAD")
    path = _endpoint(endpoint)
    found = []
    if path == "graphql":
        text = " ".join(values)
        for group, code in (("merging", "merge"), ("settings", "repo_settings")):
            for name in _mutations(data[group]["mutations"], text):
                found.append((code, "the GraphQL mutation %s is the Maintainer's" % name))
        if "createcommitonbranch" in text.casefold() and rules.names(text):
            found.append(("protected_path", "a commit made on GitHub names %s, which is %s" % rules.names(text)))
        if unread and not found:
            found.append(("command_unreadable", "gh api graphql: %s, so what it changes cannot be read" % unread[0]))
        return found
    if not writes:
        return []
    if path is None:
        return [("command_unreadable", "gh api writes with %s to an endpoint the hook cannot read" % _shown(method))]
    for pattern in data["merging"]["endpoints"]:
        if _route(pattern, path):
            found.append(("merge", "gh api %s %s merges a pull request" % (_shown(method), pattern)))
    for pattern in data["settings"]["endpoints"]:
        if _route(pattern, path):
            found.append(("repo_settings", "gh api %s %s writes the repo's rules or settings" % (_shown(method), pattern)))
    named = rules.names(path.split("/", 4)[4]) if re.match(r"repos/[^/]+/[^/]+/contents/", path) else None
    if named:
        found.append(("protected_path", "gh api %s writes %s on GitHub, which is %s" % ((_shown(method),) + named)))
    if not found and unread and "unknown" in unread[-1]:
        found.append(("command_unreadable", unread[-1]))
    return found


def github(command: str, data: dict, rules: Rules) -> list:
    """Reasons to ask about a merge, or a write to a ruleset or the repo's settings, in one Bash command."""
    try:
        commands = shell.commands(command)
    except ValueError:
        return [("command_unreadable", "the command cannot be split into words, so a merge or a write to the repo's "
                                       "settings in it cannot be read")] if GITHUB_TEXT.search(command) else []
    found = []
    for words, redirections in commands:
        at = 0
        while at < len(words) and (words[at] in PREFIXES or ASSIGNMENT.match(words[at])):
            at += 1
        if at == len(words):
            continue
        program = os.path.basename(words[at])
        if program in READS:
            continue
        if program not in ("git", "gh"):
            tool = next((i for i in range(at, len(words)) if os.path.basename(words[i]) in ("git", "gh")), None)
            heredoc = INTERPRETERS.match(program) and any("<<" in op for op, _ in redirections)
            if tool is None or not re.match(r"^(env|sudo|xargs|parallel|timeout|nice|stdbuf|caffeinate|watch)$",
                                            program):
                if program in shell.SHELLS and any(w.startswith("-") and "c" in w and not w.startswith("--")
                                                   for w in words[at + 1:]):
                    continue    # the script is read as commands of its own
                if GITHUB_TEXT.search(" ".join(words[at:])) or _mutations(
                        data["merging"]["mutations"] + data["settings"]["mutations"], " ".join(words[at:])) or (
                        heredoc and (GITHUB_TEXT.search(command) or _mutations(
                            data["merging"]["mutations"] + data["settings"]["mutations"], command))):
                    found.append(("command_unreadable", "%s runs something that names a merge, a setting or "
                                                        "GitHub's API, which the hook cannot read" % _shown(program)))
                continue
            at = tool
        program, args = os.path.basename(words[at]), words[at + 1:]
        if program == "git":
            found += _push(args, data)
            continue
        positional = _positional(args, GH_VALUED)
        if not positional:
            continue
        if positional[0] not in GH_COMMANDS:
            found.append(("command_unreadable", "gh %s is not a command the hook knows; it may be an alias or an "
                                                "extension" % _shown(positional[0])))
            continue
        if positional[:2] in (["alias", "set"], ["alias", "import"]):
            found.append(("command_unreadable", "gh alias %s makes a command the hook cannot read" % positional[1]))
            continue
        if positional[0] == "api":
            found += _api(args[args.index("api") + 1:], data, rules)
            continue
        for group, code, does in (("merging", "merge", "merges a pull request or adds one to the queue"),
                                  ("settings", "repo_settings", "writes the repo's rules or settings")):
            for entry in data[group]["commands"]:
                if positional[:len(entry.split())] == entry.split():
                    found.append((code, "gh %s %s" % (entry, does)))
    return found


def _push(args: list, data: dict) -> list:
    i = 0
    while i < len(args) and args[i].startswith("-"):
        if args[i] in GIT_VALUED:
            i += 1
        i += 1
    if args[i:i + 1] != ["push"]:
        return []
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
    if {"--all", "--mirror", "--branches"} & set(rest):
        return [("merge", "git push %s pushes every branch, %s among them" % (
            next(w for w in rest if w in ("--all", "--mirror", "--branches")), data["branch"]))]
    branch = data["branch"].casefold()
    for spec in positional[1:]:
        target = spec.lstrip("+").rsplit(":", 1)[-1].casefold()
        if re.sub(r"^refs/heads/", "", target) == branch:
            return [("merge", "git push writes %s, which only a merge from the queue writes" % data["branch"])]
    return []


# ---- the hook

def check(payload: dict, env: dict, data: dict = None, source: pathlib.Path = ROOT / "config" / "hooks.json") -> list:
    """The reasons to ask the person about this tool call, as (code, sentence); none when it is not the Maintainer's."""
    tool = payload.get("tool_name")
    if tool not in FILE_TOOLS and tool != "Bash":
        return []
    try:
        data = data or load(source)
    except Unreadable as err:
        return [("config_unreadable", "%s, so every edit and command is asked about" % err)]
    rules = Rules(data, env)
    if tool in FILE_TOOLS:
        return edit(payload, rules)
    command = (payload.get("tool_input") or {}).get("command")
    if not isinstance(command, str):
        return [("command_unreadable", "the Bash call carries no command")]
    found = Command(command, payload.get("cwd"), rules, env).read() + github(command, data, rules)
    return list(dict.fromkeys(found))


def respond(payload: dict, env: dict) -> str:
    """What the hook prints: a decision to ask, with its reasons, or nothing."""
    try:
        found = check(payload, env)
    except Exception as err:    # what the hook cannot read, it asks about
        found = [("hook_failed", "the hook could not finish (%s), so it asks" % type(err).__name__)]
    if not found:
        return ""
    # A sentence is built from config/hooks.json and the hook's own words; of the command it names only a program.
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
