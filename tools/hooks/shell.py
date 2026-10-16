"""Read a shell command as the simple commands it runs, so that a hook can see what git and gh are asked to do.

It reads words, not meaning: a variable is not expanded and a script in a file is not read. A hook
that guards something treats what this cannot read as a refusal. A here-document's body is data and
is never read as commands.
"""
from __future__ import annotations

import os
import re
import shlex

# Characters that end a word on their own. All but the redirections also end a simple command.
PUNCTUATION = ";&|()`\n<>"
SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}
# Programs that run the command string given to -c or --command, as a shell does.
STRINGS = {"flock", "script", "runuser", "su"}
STRING_OPTIONS = ("--command", "--session-command")
ENV_VALUED = {"-u", "--unset", "-C", "--chdir", "-P"}
# Words that come before the program and change nothing about what it does.
PREFIXES = {"if", "then", "else", "elif", "do", "while", "until", "!", "{", "}", "time", "command", "builtin", "exec",
            "nohup"}
# Programs that run the program their words name, git or gh among them, whatever options come first.
WRAPPERS = {"env", "sudo", "doas", "xargs", "parallel", "timeout", "gtimeout", "nice", "ionice", "chrt",
            "taskset", "numactl", "stdbuf", "gstdbuf", "caffeinate", "watch", "setsid", "flock", "chroot", "unshare",
            "nsenter", "runuser", "chpst", "unbuffer", "chronic", "script", "arch", "xcrun", "sandbox-exec",
            "systemd-run", "fakeroot", "strace", "ltrace", "dtruss", "gtime"}
HEREDOC = re.compile(r"<<(-?)[ \t]*\\?(['\"]?)([A-Za-z_][\w.-]*)\2")


def without_heredocs(text: str) -> str:
    """`text` with the body of each here-document left out. Raises ValueError if one is never ended.

    An operator counts only where the shell would read it: not inside quotes, unless inside a
    command substitution there, as in "$(cat <<'EOF' ... EOF)".
    """
    out, waiting, stack = [], [], ["code"]
    for line in text.split("\n"):
        if waiting:
            strip, word = waiting[0]
            if (line.lstrip("\t") if strip else line) == word:
                waiting.pop(0)
                out.append(line)    # kept, so that a substitution read again still ends its here-document
            continue
        out.append(line)
        i = 0
        while i < len(line):
            c, top = line[i], stack[-1]
            if top == "single":
                if c == "'":
                    stack.pop()
            elif c == "\\":
                i += 1
            elif top == "double":
                if c == '"':
                    stack.pop()
                elif line.startswith("$(", i):
                    stack.append("code")
                    i += 1
            elif c in "'\"":
                stack.append("single" if c == "'" else "double")
            elif c == "(":
                stack.append("code")
            elif c == ")" and len(stack) > 1:
                stack.pop()
            elif c == "#" and (i == 0 or line[i - 1] in " \t;&|("):
                break       # a comment runs to the end of the line
            elif line.startswith("<<", i) and not line.startswith("<<<", i):
                found = HEREDOC.match(line, i)
                if found:
                    waiting.append((found.group(1) == "-", found.group(3)))
                    i = found.end()
                    continue
            i += 1
    if waiting:
        raise ValueError("a here-document is never ended")
    return "\n".join(out)


def simple_commands(text: str) -> list:
    """Each simple command in `text`, as (words, redirection targets).

    A script given to a shell with -c or to eval, and a command substitution inside a quoted word,
    are read as well, and their commands follow. Raises ValueError when the text cannot be split
    into words, such as an unclosed quote.
    """
    return [(words, [target for _, target in redirections]) for words, redirections in commands(text)]


def commands(text: str, spend=None) -> list:
    """Each simple command in `text`, as (words, [(operator, target)]), read as simple_commands reads it.

    An operator holding '>' writes its target; one holding only '<' reads it. `spend`, if given, is called
    before each script is read, and may raise to stop a reading that has run over its budget.
    """
    if spend:
        spend()
    lex = shlex.shlex(without_heredocs(text).replace("\\\n", " "), posix=True, punctuation_chars=PUNCTUATION)
    lex.whitespace, lex.whitespace_split, lex.commenters = " \t\r", True, ""
    found, words, targets, operator = [], [], [], None
    for token in lex:
        if token and all(c in PUNCTUATION for c in token):
            if "<" in token or ">" in token:
                if words and words[-1].isdigit():
                    words.pop()     # the 2 of 2>&1
                operator = (operator or "") + token     # the next word is where it goes, not an argument
            elif words or targets:
                found.append((words, targets))
                words, targets = [], []
            continue
        if operator is not None:
            targets.append((operator, token))
            operator = None
            continue
        words.append(token)
    if words or targets:
        found.append((words, targets))
    out = []
    for words, targets in found:
        out.append((words, targets))
        out += _inner(words, spend)
        for word in words:
            for script in _substituted(word):
                out += commands(script, spend)
    return [(words, targets) for words, targets in out if words or targets]


def _inner(words: list, spend=None) -> list:
    """The commands of a script run by this one: `bash -c '...'` or `eval ...`, also after env, xargs or sudo; and
    the command string of `flock -c`, `script -c`, `runuser -c`, `su -c` and `env -S`."""
    for at, word in enumerate(words):
        name = os.path.basename(word)
        if name == "eval":
            return commands(" ".join(words[at + 1:]), spend)
        if name == "env":       # -S's string is split into the words of the command env runs, before the rest
            for i in range(at + 1, len(words)):
                if not words[i].startswith("-") and "=" not in words[i] and words[i - 1] not in ENV_VALUED:
                    break       # the program env runs: what follows is its own
                script, taken = _value(words, i, "S", ("--split-string",), True)
                if script is not None:
                    rest = words[i + 1 + taken:]
                    return commands(" ".join([script] + [shlex.quote(w) for w in rest]), spend)
        if name in SHELLS or name in STRINGS:
            script = script_of(words, at)
            return [] if script is None else commands(script, spend)
    return []


def script_of(words: list, at: int):
    """The script that words[at], a shell or a program of STRINGS, is given to run (-c), or None."""
    strings = os.path.basename(words[at]) in STRINGS
    for i in range(at + 1, len(words)):
        # A shell reads -c's script from the next word; the others take it attached too (-c'...', -qc'...').
        script, _ = _value(words, i, "c", STRING_OPTIONS if strings else (), strings)
        if script is not None:
            return script
    return None


def spelt(option: str, name: str) -> bool:
    """Whether an option, before any `=`, is the long option `name`, whole or by a prefix, as getopt and git take it."""
    return option == name or (len(option) > 2 and option.startswith("--") and name.startswith(option))


def _value(words: list, i: int, letter: str, longs: tuple, attached: bool) -> tuple:
    """(the value words[i] gives the option -<letter> or one of `longs`, whether it is the next word): alone or last
    in a bundle (-lc), the next word; with `attached`, what follows the letter. (None, False) when it gives none."""
    word = words[i]
    after = (words[i + 1], True) if i + 1 < len(words) else (None, False)
    if word.startswith("--") and any(spelt(word.partition("=")[0], long) for long in longs):
        return (word.partition("=")[2], False) if "=" in word else after
    if word.startswith("-") and not word.startswith("--") and letter in word:
        rest = word[word.index(letter) + 1:] if attached else ""
        return (rest, False) if rest else after
    return None, False


def _substituted(word: str) -> list:
    """The scripts of each $(...) and `...` inside one word, as a quoted word keeps them."""
    scripts, i = [], 0
    while i < len(word):
        if word.startswith("$(", i):
            depth, j = 1, i + 2
            while j < len(word) and depth:
                depth += {"(": 1, ")": -1}.get(word[j], 0)
                j += 1
            scripts.append(word[i + 2:j - 1] if not depth else word[i + 2:])
            i = j
        elif word[i] == "`":
            end = word.find("`", i + 1)
            scripts.append(word[i + 1:end] if end > 0 else word[i + 1:])
            i = len(word) if end < 0 else end + 1
        else:
            i += 1
    return scripts


# ---- which assignments the shell runs unconditionally, at the top level of a plain ;/newline sequence

ASSIGNMENT = re.compile(r"^[A-Za-z_]\w*=")
# POSIX special built-ins: a variable assigned before one of these persists in the shell's environment.
SPECIAL = {":", ".", "break", "continue", "eval", "exec", "exit", "export", "readonly", "return", "set", "shift",
           "times", "trap", "unset", "local", "declare", "typeset"}
# Words that open a compound command: a segment that starts with one is not a simple command whose assignment runs.
COMPOUND = {"if", "then", "else", "elif", "fi", "while", "until", "for", "do", "done", "case", "esac", "select",
            "function", "{", "}", "(", "((", "!", "time", "coproc"}
_CONNECTOR = re.compile(r"&&|\|\||[;&|\n]")
# A command substitution that names the branch the shell is on: where it runs, it is HEAD.
CURRENT_BRANCH = re.compile(r"^\$\(\s*git\s+(branch\s+--show-current|rev-parse\s+--abbrev-ref\s+HEAD|"
                            r"symbolic-ref\s+((-q|--quiet)\s+)?--short\s+HEAD)\s*\)$")


def _balanced(text: str, i: int, close: str) -> int:
    """The index just past where a run opened before `i` closes: a ) that may hold nested $( ), or a ` or }.
    Quotes inside are skipped. Runs to the end of the text when it never closes."""
    depth, quote = 0, None
    while i < len(text):
        c = text[i]
        if quote:
            quote = None if c == quote else quote
        elif c == "\\":
            i += 1
        elif c in "'\"":
            quote = c
        elif close == ")" and text.startswith("$(", i):
            i = _balanced(text, i + 2, ")") - 1
        elif c == close and (close != ")" or depth == 0):
            return i + 1
        elif close == ")" and c in "()":
            depth += 1 if c == "(" else -1
        i += 1
    return len(text)


def segments(text: str) -> list:
    """`text` split into its top-level segments, each (words, before, after): the connectors that bound it.

    A segment is the run between top-level `;`, newline, `&&`, `||`, `|` and `&`. Quotes, `( )`, `$( )`, `${ }`
    and backticks are opaque, so a separator inside one does not split. Each segment's words are built as the shell
    would: quotes are removed, but a command substitution, a parameter expansion or a subshell inside a word is
    kept whole, so an assignment's value can be told apart from a command it runs.
    """
    out, words, word, started, before, i, quote = [], [], [], False, "", 0, None

    def end_word():
        nonlocal word, started
        if started:
            words.append("".join(word))
        word, started = [], False

    def flush(after: str):
        nonlocal words, before
        end_word()
        if words or out or after:
            out.append((words, before, after))
        words, before = [], after

    while i < len(text):
        c = text[i]
        if quote:
            started = True
            if c == quote:
                quote = None
            elif c == "\\" and quote == '"' and i + 1 < len(text):
                word.append(text[i + 1])
                i += 2
                continue
            else:
                word.append(c)
            i += 1
            continue
        if c == "\\":
            word.append(text[i + 1] if i + 1 < len(text) else c)
            started = True
            i += 2
            continue
        if c in "'\"":
            quote = c
            started = True
            i += 1
            continue
        if c == "#" and not started and (i == 0 or text[i - 1] in " \t\n;&|("):
            end = text.find("\n", i)
            i = len(text) if end < 0 else end
            continue
        if c == "`" or text.startswith("$(", i) or text.startswith("${", i) or c == "(":
            close = "`" if c == "`" else "}" if text.startswith("${", i) else ")"
            start = i + (1 if c in "`(" else 2)
            end = _balanced(text, start, close)
            word.append(text[i:end])
            started = True
            i = end
            continue
        if c in " \t\r":
            end_word()
            i += 1
            continue
        found = _CONNECTOR.match(text, i) if c in ";&|\n" else None
        if found:
            flush(found.group(0))
            i += len(found.group(0))
            continue
        word.append(c)
        started = True
        i += 1
    flush("")
    return out


def touched(text: str) -> set:
    """Variable names the command changes in a way that leaves their value beyond reading: assigned more than
    once anywhere, used as a `for` variable, or touched by read, printf -v, declare/typeset -n, mapfile/readarray,
    an array assignment, or any of them reachable through eval. The empty set's complement is read, not these."""
    seen, bad = {}, set()
    for name in re.findall(r"(?:^|[\s;&|(){}`])([A-Za-z_]\w*)\+?=", text):
        seen[name] = seen.get(name, 0) + 1
    bad |= {name for name, n in seen.items() if n > 1}
    bad |= set(re.findall(r"(?:^|[\s;&|(){}`])([A-Za-z_]\w*)\[", text))      # X[0]=, an array
    bad |= set(re.findall(r"\bfor\s+(?:\(\(\s*)?([A-Za-z_]\w*)", text))
    for m in re.finditer(r"\b(read|mapfile|readarray)\b([^\n;&|]*)", text):
        bad |= set(re.findall(r"(?<![-\w])([A-Za-z_]\w*)(?![\w=])", m.group(2)))
    bad |= set(re.findall(r"\bprintf\b[^\n;&|]*?-v\s+([A-Za-z_]\w*)", text))
    bad |= set(re.findall(r"\b(?:declare|typeset|local)\b[^\n;&|]*?-\w*n\w*\s+([A-Za-z_]\w*)", text))
    if re.search(r"(?:^|[\s;&|(){}`])eval(?:[\s;&|]|$)", text):
        return set(seen) | bad | {"*"}      # eval may set anything; "*" marks every name unknown
    return bad


def _leading(words: list) -> tuple:
    """(the assignments that lead `words`, the base name of the command they run or None, its arguments). A
    transparent prefix (command, builtin, exec, nohup, time) is stepped over to reach the command it runs."""
    at = 0
    while at < len(words) and ASSIGNMENT.match(words[at]):
        at += 1
    leading, start = words[:at], at
    while start < len(words) and words[start] in PREFIXES and os.path.basename(words[start]) not in SPECIAL:
        start += 1
    if start >= len(words):
        return leading, None, []
    return leading, os.path.basename(words[start]), words[start + 1:]


def trusted_assignments(text: str) -> list:
    """The assignments and unsets the shell runs unconditionally at the top level of a plain `;`/newline sequence,
    in order, each ("set", name, value) or ("unset", name, None). An assignment counts when it leads a bare
    statement, is given to export/readonly/declare/typeset/local, or stands before a POSIX special built-in; it
    does not when it is reached through `&&` or `||`, runs in a pipeline or background subshell, or is a prefix
    before an ordinary command (there it is for that command alone). Anything in a subshell, a function or a loop
    is not read. The values are as written; a caller decides which it can read.
    """
    events = []
    try:
        segs = segments(text)
    except ValueError:
        return events
    for words, before, after in segs:
        if words is None or not words:
            continue
        if before not in ("", ";", "\n") or after in ("|", "&"):
            continue        # reached through && or ||, or run in a pipeline or background subshell: not trusted
        if words[0] in COMPOUND or (len(words) > 1 and words[1] == "(" and "=" not in words[0]):
            continue        # a compound command or a function definition, not a simple one
        leading, command, args = _leading(words)
        if command == "unset" and "-f" not in args:
            events += [("unset", name, None) for name in args if not name.startswith("-")]
        elif command is None or command in ("export", "readonly", "declare", "typeset", "local"):
            events += [("set",) + tuple(w.split("=", 1)) for w in leading + [w for w in args if ASSIGNMENT.match(w)]]
        elif command in SPECIAL:
            events += [("set",) + tuple(w.split("=", 1)) for w in leading]      # a prefix before a special built-in
    return events


def environment(text: str) -> tuple:
    """(values, present, branches): what the command leaves in the environment for the git or gh it runs, read
    fail-closed, from the assignments shell runs unconditionally at the top level (trusted_assignments).

    `values` maps a name to the plain string it is set to, when that name is set exactly once and its value is a word
    the shell would use as it stands (no expansion or substitution). `branches` are the names so set to a command
    substitution that names the branch the shell is on, which where it runs is HEAD. `present` is every name set in
    the environment, its value readable or not; `unset` takes a name out of all three.
    """
    off_limits, values, present, branches = touched(text), {}, set(), set()
    for kind, name, value in trusted_assignments(text):
        if kind == "unset":
            values.pop(name, None)
            present.discard(name)
            branches.discard(name)
            continue
        values.pop(name, None)
        branches.discard(name)
        present.add(name)
        if name in off_limits or "*" in off_limits:
            pass
        elif _plain(value):
            values[name] = value
        elif CURRENT_BRANCH.match(value):
            branches.add(name)
    return values, present, branches


def _plain(value: str) -> bool:
    """Whether the shell would put `value` in a word as it stands: no expansion, substitution or quote removal."""
    return re.match(r"^[^\s$`*?\[\]{}'\"\\]*$", value) is not None
