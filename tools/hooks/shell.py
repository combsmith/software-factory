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
    """The commands of a script run by this one: `bash -c '...'` or `eval ...`, also after env, xargs or sudo."""
    for at, word in enumerate(words):
        name = os.path.basename(word)
        if name == "eval":
            return commands(" ".join(words[at + 1:]), spend)
        if name in SHELLS:
            for i in range(at + 1, len(words) - 1):
                if words[i].startswith("-") and not words[i].startswith("--") and "c" in words[i]:
                    return commands(words[i + 1], spend)
            return []
    return []


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
