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
