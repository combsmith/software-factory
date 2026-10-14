"""Read a shell command as the simple commands it runs, so that a hook can see what git and gh are asked to do.

It reads words, not meaning: a variable is not expanded and a script in a file is not read. A hook
that guards something treats what this cannot read as a refusal.
"""
from __future__ import annotations

import os
import shlex

# Characters that end a word on their own. All but the redirections also end a simple command.
PUNCTUATION = ";&|()`\n<>"
SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}


def simple_commands(text: str) -> list:
    """Each simple command in `text`, as a list of words, redirections left out.

    A script given to a shell with -c, or to eval, is read as well and its commands follow. Raises
    ValueError when the text cannot be split into words, such as an unclosed quote.
    """
    lex = shlex.shlex(text.replace("\\\n", " "), posix=True, punctuation_chars=PUNCTUATION)
    lex.whitespace, lex.whitespace_split, lex.commenters = " \t\r", True, ""
    found, words, target = [], [], False
    for token in lex:
        if token and all(c in PUNCTUATION for c in token):
            if "<" in token or ">" in token:
                if words and words[-1].isdigit():
                    words.pop()     # the 2 of 2>&1
                target = True       # the next word is where it goes, not an argument
            elif words:
                found.append(words)
                words = []
            continue
        if target:
            target = False
            continue
        words.append(token)
    if words:
        found.append(words)
    out = []
    for words in found:
        out.append(words)
        out += _inner(words)
    return out


def _inner(words: list) -> list:
    """The commands of a script run by this one: `bash -c '...'` or `eval ...`, also after env, xargs or sudo."""
    for at, word in enumerate(words):
        name = os.path.basename(word)
        if name == "eval":
            return simple_commands(" ".join(words[at + 1:]))
        if name in SHELLS:
            for i in range(at + 1, len(words) - 1):
                if words[i].startswith("-") and not words[i].startswith("--") and "c" in words[i]:
                    return simple_commands(words[i + 1])
            return []
    return []
