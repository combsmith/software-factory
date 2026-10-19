"""Read a shell command as the simple commands it runs, so that a hook can see what git and gh are asked to do.

It reads words, not meaning: a variable is not expanded and a script in a file is not read. A hook
that guards something treats what this cannot read as a refusal. A here-document's body is data and
is never read as commands. What runs a program (a prefix, a wrapper and their options), the names a
command defines (a function, an alias), `$(which ...)` and a variable set anywhere are read here, so
that both hooks read them alike.
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
            elif top == "ansi":
                if c == "'":
                    stack.pop()
            elif top == "double":
                if c == '"':
                    stack.pop()
                elif line.startswith("$(", i):
                    stack.append("code")
                    i += 1
            elif line.startswith("$'", i):
                stack.append("ansi")        # $'...', in which a backslash escapes, \' among them
                i += 1
            elif c in "'\"":
                stack.append("single" if c == "'" else "double")
            elif c == "(":
                stack.append("code")
            elif c == ")" and len(stack) > 1:
                stack.pop()
            elif c == "#" and (i == 0 or line[i - 1] in " \t;&|()"):
                # A comment runs to the end of the line, one after a subshell's ) too: (echo A)# <<EOF opens no
                # here-document. After a substitution's ), $(x)#y, the # is in a word, and a here-document after it
                # is not seen here: its body is read as commands, which reads more, never less.
                break
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


def commands(text: str, spend=None, texts: list = None, scopes: bool = False, marked: bool = False) -> list:
    """Each simple command in `text`, as (words, [(operator, target)]), read as simple_commands reads it.

    An operator holding '>' writes its target; one holding only '<' reads it. `spend`, if given, is called
    before each script is read, and may raise to stop a reading that has run over its budget. `texts`, if
    given, gets each script read: `text`, and every script it runs (sh -c, eval, a command substitution).
    With `scopes`, the commands a substitution in a case's pattern runs come between SCOPE's two marks, which
    no command can spell: they run in a subshell, so a cd among them is theirs alone (decision 0032).
    A substitution is read only where the shell runs one: a single quote or a backslash holds it as text
    (issue 174). With `marked`, each word keeps the LIVE marks of the substitutions the shell runs in it.
    """
    if spend:
        spend()
    if texts is not None:
        texts.append(text)
    held = _held(without_heredocs(text))     # only an unquoted ; ) or > is punctuation
    lex = shlex.shlex(held, posix=True, punctuation_chars=PUNCTUATION)
    lex.whitespace, lex.whitespace_split, lex.commenters = " \t\r", True, ""
    found, words, targets, operator = [], [], [], None
    # A case's patterns are data, in every arm: from `in`, and from each ;; or ;&, to the ) that ends the pattern. Each is
    # kept in its place among the commands as (None, pattern), so that a substitution in it is read where it runs.
    arm, cases, in_pattern = [], 0, False
    for read in lex:
        punctuation, token = bool(read) and all(c in PUNCTUATION for c in read), read.translate(RETURNED)
        if in_pattern:
            if punctuation and ")" in token:
                in_pattern, arm = ";;" in token or ";&" in token, []      # `);;` ends an arm with no body
            elif punctuation and "(" in token:
                arm.append("(")         # a pattern has begun: (esac) is a pattern, not the case's end
            elif not punctuation and token == "esac" and not arm:
                cases, in_pattern = cases - 1, False
            elif not punctuation:
                arm.append(token)
                found.append((None, token))
            continue
        if punctuation:
            if "<" in token or ">" in token:
                if words and words[-1].isdigit():
                    words.pop()     # the 2 of 2>&1
                operator = (operator or "") + token     # the next word is where it goes, not an argument
                continue
            if words or targets:
                found.append((words, targets))
                words, targets = [], []
            in_pattern = cases > 0 and (";;" in token or ";&" in token)
            continue
        if operator is not None:
            targets.append((operator, token))
            operator = None
            continue
        if token == "esac" and cases and not words:
            cases -= 1
            continue
        words.append(token)
        if token == "in" and words[-3:-2] == ["case"] and set(words[:-3]) <= OPENERS | NEUTRAL:
            found.append((words, targets))      # case WORD in: what follows, to a ), is a pattern
            words, targets, cases, in_pattern = [], [], cases + 1, True
    if words or targets:
        found.append((words, targets))
    if cases or in_pattern:
        raise ValueError("a case is never ended")
    out = []
    for words, targets in found:
        if words is None:       # a pattern runs nothing, but a substitution in it does, where the pattern stands
            for script in _substituted(targets, spend):
                read = commands(script, spend, texts, scopes, marked)
                out += [SCOPE[0]] + read + [SCOPE[1]] if scopes else read
            continue
        plain = [unmarked(word) for word in words]
        out.append((words, targets) if marked else (plain, [(op, unmarked(target)) for op, target in targets]))
        out += _inner(plain, spend, texts, marked)
        for word in words:
            for script in _substituted(word, spend):
                out += commands(script, spend, texts, scopes, marked)
    return [(words, targets) for words, targets in out if words or targets]


# The marks commands(scopes=True) puts around what a case pattern's substitution runs: no words, so no command spells one.
SCOPE = ((None, "("), (None, ")"))


# Each character that ends a word or a command, as it stands while a quote or a backslash holds it: one of the Unicode
# private use area, so that shlex reads it as part of a word and never as punctuation. It is given back in every word.
HOLDS = {c: chr(0xE000 + ord(c)) for c in PUNCTUATION}
RETURNED = {ord(held): c for c, held in HOLDS.items()}
# The $ of a $( and a backtick that the shell runs, in double quotes, as each stands in a word commands reads: so that a
# substitution a single quote or a backslash holds is told from one the shell runs, once the quotes are gone (issue
# 174). commands(marked=True) keeps them in the words it gives; unmarked() gives the text back.
LIVE = {c: chr(0xE100 + ord(c)) for c in "$`"}
# A $ or a backtick a backslash holds in double quotes: the shell takes the backslash out and the character is text. It
# is marked, as a LIVE one is, so that an alias's value tells it from one that expands (decision 0030).
ESCAPED = {c: chr(0xE200 + ord(c)) for c in "$`"}
UNLIVE = {ord(mark): c for marks in (LIVE, ESCAPED) for c, mark in marks.items()}
# What comes before a word: where a ( is the shell's own. A carriage return is no break.
BREAKS = " \t\n;&|()<>"
# What a # that begins a comment comes after. After < or >, the shell's comment leaves a redirection with no target,
# which it refuses to run, so the hook reads the # as a word, as it did before (issue 174).
COMMENTS_AFTER = " \t\n;&|("
# What ends a command, so that the next word is a command again; and what ends a word, too.
ENDS = ";&|()\n"
WORD_ENDS = " \t\r" + ENDS
# Reserved words after which the next word is a command again: a ( there opens a subshell or an arithmetic command.
AGAIN = {"if", "then", "else", "elif", "while", "until", "do", "!", "{", "time", "for"}
# How a $'...' with a backslash is refused: the hook decodes none, so bash and zsh cannot read it differently from the
# hook (issue 174, ruling R1). Its message says to write any message to a file.
ANSI_REFUSED = "a $'...' holds a backslash, which the hook does not decode; write any message to a file and use -F"


def unmarked(word: str) -> str:
    """`word` with each LIVE mark made the `$` or backtick it marks."""
    return word.translate(UNLIVE)


def ansi_end(text: str, i: int) -> int:
    """The index past the closing quote of a $'...' whose body starts at text[i]. Raises ValueError when the body holds
    a backslash (ANSI_REFUSED: the hook decodes none, ruling R1) or when it never closes."""
    while i < len(text):
        if text[i] == "\\":
            raise ValueError(ANSI_REFUSED)
        if text[i] == "'":
            return i + 1
        i += 1
    raise ValueError("No closing quotation")


def _literal(text: str) -> str:
    """`text` spelt so that shlex reads it as one literal word, each character of PUNCTUATION held."""
    if any(ord(c) in RETURNED or ord(c) in UNLIVE for c in text):
        raise ValueError("the command decodes to a character the reader keeps for what a quote holds")
    held = text.translate({ord(c): mark for c, mark in HOLDS.items()})
    return "\\'".join("'%s'" % part for part in held.split("'"))


def _touches(text: str, i: int) -> bool:
    """Whether the unquoted ( at text[i], after a word, is one the hook cannot read: a zsh alternation or glob
    qualifier, or an extglob (.g(i|x)t, *(.), @(a|b)). The shell's own are not: $( and $((, =( with NAME=( and
    NAME+=(, and a function's NAME()."""
    return text[i - 1] not in "$=" and text[i + 1:i + 2] != ")"


def _opens(text: str, i: int, starts: bool, words: int) -> bool:
    """Whether the unquoted ( at text[i] that begins a word is the shell's own: where a command begins (a subshell, an
    arithmetic command), after < or > (a process substitution), or a function's NAME (). Elsewhere it begins an
    argument, and is a zsh glob group, (.git|x), that the hook does not read (issue 174)."""
    return starts and (words == 0 or text[i - 1] in "<>" or text[i + 1:i + 2] == ")")


def _held(text: str) -> str:
    """`text` as shlex in posix mode should read it, as the shell reads it: each character of PUNCTUATION that a quote
    or a backslash holds made its HOLDS; a $( or a backtick the shell runs in double quotes marked with LIVE; in double
    quotes, \\$ and \\` made the text they are, marked ESCAPED; a comment, from an unquoted # that begins a word, outside
    a ${...}, to the end of its line, left out; a $'...' with no backslash as a single-quoted word, one with a backslash
    refused (ansi_end), and $"..." as "..."; and a backslash
    before a newline, outside single quotes, taken out with it. Raises ValueError where what a quote holds cannot be
    told: a quote or a backslash left open, text that already holds a character of HOLDS, LIVE or ESCAPED, or a ( the
    hook does not read, touching a word (_touches) or beginning an argument (_opens). The ( of an arithmetic command or
    expansion, and of a ${...}, are their own."""
    if any(ord(c) in RETURNED or ord(c) in UNLIVE for c in text):
        raise ValueError("the command holds a character the reader keeps for what a quote holds")
    out, quote, i, starts = [], None, 0, True       # starts: the next character begins a word
    comments = True     # and a # there begins a comment
    # Where an arithmetic command or expansion, (( or $((, and a ${...}, that began ends: what they hold is their own.
    arithmetic = braces = 0
    words, first, word = 0, None, ""        # the words the simple command has so far, its first, and the one being read
    opened = []     # for each ( not yet closed, where the command stood before it, if it stands in a word: <( >( $(
    while i < len(text):
        c = text[i]
        if c == "\\" and quote != "'":
            if i + 1 >= len(text):
                raise ValueError("No escaped character")
            after = text[i + 1]
            if quote == '"' and after in ESCAPED:
                out.append(ESCAPED[after])
            elif after != "\n":     # a backslash before a newline is a line continuation: the two lines are one
                out.append(c + HOLDS.get(after, after))
            starts, comments, word = starts and after == "\n", comments and after == "\n", word + c
            i += 2
            continue
        if quote is None:
            if c == "$" and i >= braces and text.startswith("${", i):
                braces = _balanced(text, i + 2, "}")
            if c == "#" and comments and i >= braces:
                end = text.find("\n", i)
                i = len(text) if end < 0 else end
                continue
            if i < braces and (c in PUNCTUATION or c == "`" or text.startswith("$(", i)):
                # In a ${...} each is part of the word, zsh's ${(L)f} too, and a substitution in it runs: ${x:-`cmd`}.
                out.append(LIVE[c] if c == "`" or c == "$" else HOLDS[c])
                starts, comments, word = False, False, word + c
                i += 1
                continue
            if c == "$" and text.startswith("$'", i):
                # $'...' with a backslash is refused (ansi_end, ruling R1); with none it is a single-quoted word.
                end = ansi_end(text, i + 2)
                out.append(_literal(text[i + 2:end - 1]))
                starts, comments, word = False, False, word + "'"
                i = end
                continue
            if c == "$" and text.startswith('$"', i):
                i += 1
                continue
            # A process substitution's or a command substitution's ( and ) stand in a word: after its ), the command
            # goes on where it was. Any other ) ends what it closed, and what follows is a command again.
            kept = None
            if c == "(":
                if text.startswith("((", i) and i >= arithmetic and (text[i - 1:i] == "$" or (starts and words == 0)):
                    arithmetic = _balanced(text, i + 1, ")")
                if i >= arithmetic and (_touches(text, i) if not starts else not _opens(text, i, starts, words)):
                    raise ValueError("a ( in a word is a pattern the hook does not read")
                opened.append((words, first, word) if text[i - 1:i] in ("<", ">", "$") and i else None)
            elif c == ")" and opened:
                kept = opened.pop()
            if kept is not None:
                words, first, word = kept[0], kept[1], kept[2] + c
            else:
                if c in WORD_ENDS and word:
                    words += 1
                    first = word if words == 1 else first
                    if word in AGAIN or (word == "in" and first == "case"):
                        words = 0       # the next word is a command again
                    word = ""
                if c in ENDS:
                    words, first = 0, None
                elif c not in " \t\r<>":
                    word += c
            quote = c if c in "'\"" else None
            out.append(c)
            starts = c in BREAKS and c != ")"       # a ) may end a substitution inside a word: $(x)#y is one word
            comments = c in COMMENTS_AFTER
        elif c == quote:
            quote, comments = None, False
            out.append(c)
        elif quote == '"' and (c == "`" or text.startswith("$(", i)):
            out.append(LIVE[c])
        else:
            out.append(HOLDS.get(c, c))
        i += 1
    if quote:
        raise ValueError("No closing quotation")
    return "".join(out)


def _inner(words: list, spend=None, texts: list = None, marked: bool = False) -> list:
    """The commands of a script run by this one: `bash -c '...'` or `eval ...`, also after env, xargs or sudo; and
    the command string of `flock -c`, `script -c`, `runuser -c`, `su -c` and `env -S`. `words` are as the shell gives
    them, with no LIVE mark: the script is read again as text."""
    for at, word in enumerate(words):
        name = os.path.basename(word)
        if name == "eval":
            return commands(" ".join(words[at + 1:]), spend, texts, marked=marked)
        if name == "env":       # -S's string is split into the words of the command env runs, before the rest
            for i in range(at + 1, len(words)):
                if not words[i].startswith("-") and "=" not in words[i] and words[i - 1] not in ENV_VALUED:
                    break       # the program env runs: what follows is its own
                script, taken = _value(words, i, "S", ("--split-string",), True)
                if script is not None:
                    rest = words[i + 1 + taken:]
                    return commands(" ".join([script] + [shlex.quote(w) for w in rest]), spend, texts, marked=marked)
        if name in SHELLS or name in STRINGS:
            script = script_of(words, at)
            return [] if script is None else commands(script, spend, texts, marked=marked)
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


def substitutions(word: str, spend=None, depth: int = 0) -> list:
    """(where it starts, where it ends, its script) of each substitution the shell runs in one word, as commands(marked=
    True) gives it: a $(...) or `...` that LIVE marks. One a single quote or a backslash held is text (issue 174).
    `spend`, if given, is called before each arithmetic expansion is read; past NESTED_MOST of them, one in another, it
    raises ValueError: a reading the hook would cut short is one it cannot read."""
    if LIVE["$"] not in word and LIVE["`"] not in word:
        return []       # most words hold none: read in one step, not a letter at a time
    spans, i, plain = [], 0, unmarked(word)
    while i < len(word):
        if word[i] == LIVE["$"]:
            j = _balanced(plain, i + 2, ")")     # a ( or ) a quote of the script's own holds is data: '%s)'
            if plain[j - 1:j] != ")":
                # It never closes as the shell reads it, which only data a quote held may do: read to its first ), as
                # though a # began no comment, so that what it holds is still read.
                j = _balanced(plain, i + 2, ")", comments=False)
            if plain.startswith("$((", i) and plain[j - 2:j] == "))":
                # An arithmetic expansion runs no command, but a substitution inside it runs.
                if spend:
                    spend()
                if depth >= NESTED_MOST:
                    raise ValueError("arithmetic expansions are nested deeper than the hook reads")
                spans += [(i + 3 + start, i + 3 + end, script)
                          for start, end, script in substitutions(word[i + 3:j - 2], spend, depth + 1)]
            else:
                spans.append((i, j, plain[i + 2:j - 1] if plain[j - 1:j] == ")" else plain[i + 2:]))
            i = j
        elif word[i] == LIVE["`"]:
            end = word.find(LIVE["`"], i + 1)
            spans.append((i, len(word) if end < 0 else end + 1, plain[i + 1:end] if end > 0 else plain[i + 1:]))
            i = len(word) if end < 0 else end + 1
        else:
            i += 1
    return spans


NESTED_MOST = 64     # arithmetic expansions read one inside another, at most


def _substituted(word: str, spend=None) -> list:
    """The scripts of each substitution the shell runs inside one word (substitutions)."""
    return [script for _, _, script in substitutions(word, spend)]


def held(word: str) -> list:
    """The scripts of each $(...) and `...` that a single quote or a backslash holds in one word, as commands(marked=
    True) gives it: text the shell does not run where it stands, but which a program given it may run later (trap,
    eval, an arithmetic expansion of a variable). Those the shell runs, and what they hold, are left out: they are
    read where they run."""
    if "$(" not in word and "`" not in word and ESCAPED["$"] not in word and ESCAPED["`"] not in word:
        return []       # most words hold none: read in one step, not a letter at a time
    text = list(word)
    for start, end, _ in substitutions(word):
        text[start:end] = " " * (end - start)
    text = unmarked("".join(text).translate({ord(mark): " " for mark in LIVE.values()}))
    scripts, i = [], 0
    while i < len(text):
        if text.startswith("$(", i):
            j = _balanced(text, i + 2, ")")
            scripts.append(text[i + 2:j - 1] if text[j - 1:j] == ")" else text[i + 2:])
            i = j
        elif text[i] == "`":
            end = text.find("`", i + 1)
            scripts.append(text[i + 1:end] if end > 0 else text[i + 1:])
            i = len(text) if end < 0 else end + 1
        else:
            i += 1
    return scripts


def requoted(word: str) -> str:
    """`word`, as commands(marked=True) gives it, spelt so that commands reads it again as the same word: each
    substitution the shell runs in it as one in double quotes, and the rest held by single quotes."""
    out, last = [], 0
    for start, end, script in substitutions(word):
        if start > last:
            out.append(shlex.quote(unmarked(word[last:start])))
        out.append('"$(%s)"' % script.replace("\\", "\\\\").replace('"', '\\"'))
        last = end
    return "".join(out + ([shlex.quote(unmarked(word[last:]))] if last < len(word) or not out else []))


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


def _balanced(text: str, i: int, close: str, comments: bool = True) -> int:
    """The index just past where a run opened before `i` closes: a ) that may hold nested $( ), or a ` or }.
    Quotes inside are skipped, and so are a parameter expansion's `${...}` and, in a `( )` and with `comments`, a
    comment (decision 0032). Runs to the end of the text when it never closes."""
    depth, quote, start = 0, None, i
    while i < len(text):
        c = text[i]
        if quote:
            quote = None if c == quote else quote
        elif c == "\\":
            i += 1
        elif text.startswith("$'", i):
            i = (ansi_end(text, i + 2) or len(text)) - 1        # $'...', in which a backslash escapes
        elif c in "'\"":
            quote = c
        elif text.startswith("${", i):
            i = _balanced(text, i + 2, "}") - 1
        elif comments and close == ")" and c == "#" and (i == start or text[i - 1] in " \t\n;&|()"):
            end = text.find("\n", i)        # a comment runs to the end of its line
            i = (len(text) if end < 0 else end) - 1
        elif text.startswith("$(", i):      # a substitution nested in any run, ${...} too, is its own
            i = _balanced(text, i + 2, ")") - 1
        elif c == close and (close != ")" or depth == 0):
            return i + 1
        elif close == ")" and c in "()":
            depth += 1 if c == "(" else -1
        i += 1
    return len(text)


def segments(text: str) -> list:
    """`text` split into its top-level segments, each (words, before, after, start): the connectors that bound it
    and where it starts in `without_heredocs(text)`. Raises ValueError when a here-document is never ended.

    A here-document's body is data and is left out first. A segment is the run between top-level `;`, newline,
    `&&`, `||`, `|` and `&`; a newline right after `&&`, `||` or `|` continues the list, as the shell reads it.
    Quotes, `( )`, `$( )`, `${ }` and backticks are opaque, so a separator inside one does not split, and a
    backslash before a newline joins the lines. Each segment's words are built as the shell would: quotes are
    removed and a `$'...'` with no backslash is a single-quoted word (issue 174), but a command substitution, a parameter
    expansion or a subshell inside a word is kept whole, so an assignment's value can be told apart from a command it
    runs. Raises ValueError, too, for a `$'...'` that never closes or holds a backslash, which the hook does not decode
    (ansi_end).
    """
    text = without_heredocs(text)
    out, words, word, started, before, i, quote, start = [], [], [], False, "", 0, None, 0

    def end_word():
        nonlocal word, started
        if started:
            words.append("".join(word))
        word, started = [], False

    def flush(after: str):
        nonlocal words, before
        end_word()
        if not words and before in ("&&", "||", "|") and after == "\n":
            return      # the list goes on past the newline: what follows is still reached through `before`
        if words or out or after:
            out.append((words, before, after, start))
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
        if c == "\\" and text.startswith("\n", i + 1):
            i += 2      # a line continuation: the two lines are one
            continue
        if c == "\\":
            word.append(text[i + 1] if i + 1 < len(text) else c)
            started = True
            i += 2
            continue
        if text.startswith("$'", i):    # $'...' with a backslash is refused (ansi_end); with none it is single-quoted
            end = ansi_end(text, i + 2)
            word.append(text[i + 2:end - 1])
            started = True
            i = end
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
            start = i
            continue
        word.append(c)
        started = True
        i += 1
    flush("")
    return out


NAME = r"[A-Za-z_]\w*"
# ${X:=v} and ${X=v} assign X wherever they are expanded, inside quotes, a substitution or a here-document too.
DEFAULT_ASSIGN = re.compile(r"\$\{(%s):?=" % NAME)
# Arithmetic assigns too: $((X=1)), ((X++)), let X=1.
ARITHMETIC = re.compile(r"\(\((.*?)\)\)", re.S)
ARITH_ASSIGN = re.compile(r"(%s)\s*(?:\+\+|--|(?:[-+*/%%&|^]|<<|>>)?=(?!=))|(?:\+\+|--)\s*(%s)" % (NAME, NAME))


# Built-ins that write the variables their words name.
WRITERS = {"printf", "declare", "typeset", "local", "export", "readonly", "read", "mapfile", "readarray", "let",
           "unset"}


def _indirect(words: list) -> bool:
    """Whether a writer (words[0]) is given a target it computes at run time, or a name reference: printf -v "$N",
    declare "$N=v", read $N, let "$N=1", declare -n, and the like. Only a literal identifier can be read."""
    writer, args = words[0], words[1:]
    if writer in ("declare", "typeset", "local") and any(re.match(r"^-\w*n", a) for a in args):
        return True     # a name reference: a write to it writes another variable
    if writer == "printf":
        targets = [args[i + 1] for i, a in enumerate(args[:-1]) if a == "-v"]
        targets += [a[2:] for a in args if a.startswith("-v") and a != "-v"]
    else:
        targets = [a.split("=", 1)[0] for a in args if not a.startswith(("-", "+"))]
    return any("$" in t or "`" in t for t in targets)


def assigned_elsewhere(text: str) -> set:
    """Names the command may assign in the current shell where no assignment word shows it: a default-value
    expansion (${X:=v}, ${X=v}) or arithmetic ($((X=1)), ((X++)), let X=1), anywhere in the text."""
    names = set(DEFAULT_ASSIGN.findall(text))
    for body in ARITHMETIC.findall(text) + re.findall(r"\blet\b([^\n;&|]*)", text):
        names |= {a or b for a, b in ARITH_ASSIGN.findall(body)}
    return names


def touched(text: str) -> set:
    """Variable names the command changes in a way that leaves their value beyond reading: assigned more than
    once anywhere (in any context, quoted or not), unset anywhere, used as a for/select/getopts variable, touched by
    read, printf -v, declare/typeset -n, mapfile/readarray, an array assignment, a default-value expansion or
    arithmetic. eval, source and `.` may set anything, and "*" then marks every name unknown, as does a
    here-document that is never ended."""
    try:
        stripped, segs = without_heredocs(text), segments(text)
    except ValueError:
        return {"*"}
    seen, quoted = {}, {}
    for name in re.findall(r"(?:^|[\s;&|(){}`])(%s)\+?=" % NAME, stripped):
        seen[name] = seen.get(name, 0) + 1
    bad = set()
    for words, _, _, _ in segs:     # words with their quotes removed: export "X=v" assigns X too
        for at, word in enumerate(words):
            found = re.match(r"^(%s)\+?=" % NAME, word)
            if found:
                quoted[found.group(1)] = quoted.get(found.group(1), 0) + 1
            if word in ("read", "mapfile", "readarray", "unset"):      # whatever position: then, &&, a loop
                bad |= {w for w in words[at + 1:] if re.fullmatch(NAME, w)}
            if word in WRITERS and _indirect(words[at:]):
                return {"*"}        # it writes a variable whose name the command computes: any may change
        _, command, _ = _leading(_commands_of(words))
        if command in ("source", ".", "eval"):
            return {"*"}
    if re.search(r"\$\{!%s:?=" % NAME, text) or any("$" in body and re.search(r"(?<![=!<>])=(?!=)", body)
                                                       for body in ARITHMETIC.findall(text)):
        return {"*"}        # ${!N:=v}, (( $N = 1 )): an assignment to a variable named at run time
    counts = {name: max(seen.get(name, 0), quoted.get(name, 0)) for name in set(seen) | set(quoted)}
    bad |= {name for name, n in counts.items() if n > 1}
    bad |= set(re.findall(r"(?:^|[\s;&|()}`])(%s)\[" % NAME, stripped))      # X[0]=, an array; ${X[0]} reads one
    bad |= set(re.findall(r"\b(?:for|select)\s+(?:\(\(\s*)?(%s)" % NAME, stripped))
    bad |= set(re.findall(r"\bgetopts\s+\S+\s+(%s)" % NAME, stripped))
    bad |= set(re.findall(r"\bprintf\b[^\n;&|]*?-v\s+(%s)" % NAME, stripped))
    bad |= set(re.findall(r"\b(?:declare|typeset|local)\b[^\n;&|]*?-\w*n\w*\s+(%s)" % NAME, stripped))
    bad |= assigned_elsewhere(text)     # the raw text: an unquoted here-document's body is expanded too
    if re.search(r"(?:^|[\s;&|(){}`])eval(?:[\s;&|]|$)", stripped):
        return set(counts) | bad | {"*"}
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


# Reserved words at command position: these open and close a compound command's body.
OPENERS = {"if", "while", "until", "for", "select", "case", "{"}
CLOSERS = {"fi", "done", "esac", "}"}
NEUTRAL = {"then", "do", "else", "elif", "!", "time", "coproc"}
DECLARERS = ("export", "readonly", "declare", "typeset", "local")
GIT_OR_GH = re.compile(r"(?<![\w.-])(git|gh)(?![\w.-])")


def _commands_of(words: list) -> list:
    """A segment's words from its command on: leading reserved words, a `case WORD in` and its pattern, and a
    function definition's head (`name() {`, `function name {`) stepped over. Empty when the segment runs no simple
    command: a `for`/`select` head, or a function whose body is a ( ) subshell."""
    at = 0
    while at < len(words) and words[at] in OPENERS | CLOSERS | NEUTRAL | {"function"}:
        if words[at] in ("for", "select"):
            return []
        if words[at] == "case":
            at = words.index("in", at) + 1 if "in" in words[at:] else len(words)
            continue
        if words[at] == "function":
            at += 2 + (words[at + 2:at + 3] == ["()"])
            continue
        at += 1
    rest = words[at:]
    if rest and (rest[0].endswith("()") or rest[1:2] == ["()"]):
        rest = rest[1:] if rest[0].endswith("()") else rest[2:]
        if rest and rest[0].startswith("("):
            return []       # the body is a subshell: nothing in it persists
        rest = rest[1:] if rest[:1] == ["{"] else rest
    while rest and rest[0] in OPENERS | CLOSERS | NEUTRAL:
        rest = rest[1:]
    if rest and rest[0].endswith(")") and not rest[0].startswith("(") and not ASSIGNMENT.match(rest[0]):
        rest = rest[1:]     # a case pattern: a)
    return rest


def _persisting(words: list, functions: set) -> tuple:
    """(assignments that persist with their value, assignments that may persist, names unset) of a simple command.

    A bare assignment, or one given to export, readonly, declare or typeset, persists in every shell. These may
    persist, depending on the shell, and so are set with their value unread: a prefix before a special built-in
    (POSIX sh keeps it; bash and zsh do not) or before a function the command defines (POSIX sh keeps it), and
    `local` outside a function (zsh sets it; bash refuses). A prefix before any other command is for it alone."""
    leading, command, args = _leading(words)
    given = [w for w in args if ASSIGNMENT.match(w)]
    if command == "unset":
        return [], [], ([] if "-f" in args else [w for w in args if not w.startswith("-")])
    if command is None:
        return leading, [], []
    if command in ("export", "readonly", "declare", "typeset"):
        return given, leading, []
    if command == "local":
        return [], leading + given, []
    if command in SPECIAL or command in functions:
        return [], leading, []
    return [], [], []


def trusted_assignments(text: str) -> list:
    """What the command assigns and unsets in the shell, in order, as ("set", name, value), ("unset", name, None)
    and ("maybe", name, None).

    "set" and "unset" are what runs unconditionally at the top level of a plain `;`/newline sequence: not reached
    through `&&` or `||`, not in a pipeline or background subshell, and not inside any compound command's body
    (if, while, until, for, select, case, a `{ }` group, a function), tracked by its reserved words at command
    position. An assignment persists when it is bare, given to export/readonly/declare/typeset/local, or a prefix
    before a POSIX special built-in. Order matters: an unset after any git or gh is not trusted (that command ran
    with the name set), and an assignment is "maybe" when the name is used before it. Every other persisting
    assignment, wherever it stands, is "maybe": set, its value unread. If the reserved words do not balance,
    nothing is trusted and every assignment is "maybe". A here-document's body is left out.
    """
    try:
        stripped, segs = without_heredocs(text), segments(text)
    except ValueError:
        return []
    events, depth, balanced = [], 0, True
    functions = {a or b for a, b in re.findall(
        r"(?:^|[\s;&|(){}])(?:function\s+(%s)|(%s)\s*\(\s*\))" % (NAME, NAME), stripped)}
    named = GIT_OR_GH.search(stripped)      # where git or gh is first named: searched once, not before every segment
    named = len(stripped) if named is None else named.start()
    for words, before, after, start in segs:
        if not words:
            continue
        outer = depth
        for word in words:
            if word in OPENERS:
                depth += 1
            elif word in CLOSERS:
                depth -= 1
                balanced = balanced and depth >= 0
            elif word not in NEUTRAL:
                break
            if word in ("for", "select", "case"):
                break
        if words[0] == "function" or (words[0].endswith("()") or words[1:2] == ["()"]):
            depth += "{" in words       # the body's `{` on the same line opens it; on the next line it opens itself
        commands = _commands_of(words)
        given, maybe, unset = _persisting(commands, functions) if commands else ([], [], [])
        trusted = (outer == 0 and commands == words and before in ("", ";", "\n") and after not in ("|", "&")
                   and not words[0].startswith("("))
        for word in given:
            name, _, value = word.partition("=")
            used = re.search(r"\$\{?%s(?!\w)" % re.escape(name), stripped[:start])
            events.append(("set", name, value) if trusted and not used else ("maybe", name, None))
        events += [("maybe", word.split("=", 1)[0], None) for word in maybe]
        if trusted and named >= start:
            events += [("unset", name, None) for name in unset]
    if depth != 0 or not balanced:
        return [("maybe", name, None) for kind, name, _ in events if kind != "unset"]
    return events


def environment(text: str) -> tuple:
    """(values, present, branches): what the command leaves in the environment for the git or gh it runs, read
    fail-closed from trusted_assignments.

    `values` maps a name to the plain string it is set to, when a trusted assignment sets it, nothing else touches
    it, and its value is a word the shell would use as it stands. `branches` are the names so set to a command
    substitution that names the branch the shell is on, which where it runs is HEAD. `present` is every name that
    may be set, its value readable or not: a trusted unset takes a name out; nothing else does.
    """
    off_limits, values, present, branches = touched(text), {}, set(), set()
    for kind, name, value in trusted_assignments(text):
        values.pop(name, None)
        branches.discard(name)
        if kind == "unset":
            present.discard(name)
            continue
        present.add(name)
        if kind == "maybe" or name in off_limits or "*" in off_limits:
            pass
        elif _plain(value):
            values[name] = value
        elif CURRENT_BRANCH.match(value):
            branches.add(name)
    for name in assigned_elsewhere(text):
        present.add(name)
        values.pop(name, None)
        branches.discard(name)
    return values, present, branches


def _plain(value: str) -> bool:
    """Whether the shell would put `value` in a word as it stands: no expansion, substitution or quote removal."""
    return re.match(r"^[^\s$`*?\[\]{}'\"\\]*$", value) is not None


# ---- what runs a program: prefixes and wrappers, read alike by both hooks

# Words before a program that change nothing about what runs, and the options of theirs that take the next word.
PREFIXED = {"exec": {"-a"}, "time": {"-f", "--format", "-o", "--output"}, "command": set(), "builtin": set(),
            "nohup": set()}
# Reserved words that open or go on with a compound command: before a program, they change nothing of what it runs.
RESERVED = PREFIXES - set(PREFIXED)
# The options of xargs and parallel that take the next word, and those of npx and its like.
FEED_VALUED = {"-I", "-L", "-n", "-P", "-s", "-d", "-E", "-a", "--max-args", "--max-procs", "--delimiter",
               "--arg-file", "--max-lines", "--replace", "--eof", "-j", "--jobs"}
# The wrappers that give the program they run words read from their input, which the command's words do not show.
FEEDERS = {"xargs", "parallel"}
NPX_VALUED = {"-p", "--package", "--cache", "--userconfig", "--registry", "-w", "--workspace"}
# What runs the program its words name, after its own: for each, its options that take the next word as their value,
# and how many words that are not options come before the program (timeout's duration, chroot's new root). The first
# word past them is the program; what follows is that program's, and data to any other.
WRAPPED = {
    "env": ({"-u", "--unset", "-C", "--chdir", "-P"}, 0),
    "sudo": ({"-u", "--user", "-g", "--group", "-h", "--host", "-p", "--prompt", "-C", "--close-from", "-D",
              "--chdir", "-R", "--chroot", "-r", "--role", "-t", "--type", "-T", "--command-timeout", "-U",
              "--other-user"}, 0),
    "doas": ({"-u", "-C"}, 0),
    "xargs": (FEED_VALUED, 0), "parallel": (FEED_VALUED, 0),
    "timeout": ({"-s", "--signal", "-k", "--kill-after"}, 1), "gtimeout": ({"-s", "--signal", "-k", "--kill-after"}, 1),
    "nice": ({"-n", "--adjustment"}, 0),
    "ionice": ({"-c", "--class", "-n", "--classdata", "-p", "--pid", "-P", "--pgid", "-u", "--uid"}, 0),
    "chrt": (set(), 1), "taskset": (set(), 1),
    "numactl": ({"-N", "--cpunodebind", "-m", "--membind", "-C", "--physcpubind", "-p", "--preferred", "-i",
                 "--interleave"}, 0),
    "stdbuf": ({"-i", "-o", "-e", "--input", "--output", "--error"}, 0),
    "gstdbuf": ({"-i", "-o", "-e", "--input", "--output", "--error"}, 0),
    "caffeinate": ({"-t", "-w"}, 0), "watch": ({"-n", "--interval"}, 0), "setsid": (set(), 0),
    "flock": ({"-w", "--wait", "--timeout", "-E", "--conflict-exit-code"}, 1),
    "chroot": ({"--userspec", "--groups"}, 1),
    "unshare": ({"-S", "--setuid", "-G", "--setgid", "-R", "--root", "-w", "--wd"}, 0),
    "nsenter": ({"-t", "--target", "-S", "--setuid", "-G", "--setgid"}, 0),
    "runuser": ({"-u", "--user", "-g", "--group", "-G", "--supp-group", "-s", "--shell"}, 0),
    "chpst": ({"-u", "-U", "-e", "-/", "-n", "-l", "-L", "-m", "-d", "-o", "-p", "-f", "-c"}, 0),
    "unbuffer": (set(), 0), "chronic": (set(), 0), "arch": (set(), 0), "corepack": (set(), 0),
    "script": ({"-t", "--timing", "-T", "-I", "-O", "-B", "--log-in", "--log-out", "--log-io", "-E", "-o"}, 1),
    "xcrun": ({"--sdk", "--toolchain", "-sdk", "-toolchain"}, 0),
    "sandbox-exec": ({"-f", "-n", "-p", "-D"}, 0),
    "systemd-run": ({"-p", "--property", "-u", "--unit", "-E", "--setenv", "--uid", "--gid", "-M", "--machine",
                     "--description", "--slice", "--working-directory", "-H", "--host", "--nice"}, 0),
    "fakeroot": ({"-l", "--lib", "--faked", "-s", "-i", "-b"}, 0),
    "strace": ({"-o", "-e", "-p", "-s", "-u", "-E", "-P", "-I", "-a", "-b", "-S", "-O", "-X"}, 0),
    "ltrace": ({"-o", "-e", "-p", "-s", "-u", "-n", "-a", "-A", "-l", "-x", "-F"}, 0),
    "dtruss": ({"-p", "-n", "-t", "-W"}, 0), "gtime": ({"-f", "--format", "-o", "--output"}, 0),
    "npx": (NPX_VALUED, 0), "pnpx": (NPX_VALUED, 0), "bunx": (NPX_VALUED, 0),
}
# The prefixes and wrappers a commit or a push may run under (decision 0024): each runs the program its words name as
# it is, as the same user and from the same PATH. env only with assignments, and command only with no option (-p looks
# in another PATH). Any other, sudo, exec, env -i, env -C and xargs among them, runs a git the identity hook cannot read.
AS_IS = {"env", "nice", "nohup", "timeout", "stdbuf", "caffeinate", "time", "command"}


def past_prefixes(words: list, at: int = 0) -> tuple:
    """(the index past the prefixes, assignments and reserved words from `at`, [(each prefix, its options)]). The index
    is None when a prefix runs nothing: command -v names a program and runs none."""
    passed = []
    while at < len(words):
        word = words[at]
        if word in PREFIXES:
            at += 1
            options = []
            while word in PREFIXED and at < len(words) and words[at].startswith("-") and words[at] != "-":
                if words[at] == "--":
                    at += 1
                    break
                if word == "command" and re.match(r"^-[pP]*[vV]", words[at]):
                    return None, passed        # command -v names a program and runs none
                options.append(words[at])
                at += 2 if words[at] in PREFIXED[word] else 1
            passed.append((word, options))
        elif ASSIGNMENT.match(word):
            at += 1
        elif word == "function":    # its names, one or (zsh) more, up to the body
            at += 1
            while at < len(words) and words[at] not in ("{", "()") and not words[at].startswith("("):
                at += 1
        else:
            break
    return at, passed


def past_wrapper(words: list, at: int, program: str, strings=()) -> tuple:
    """(the index of the program the wrapper `program` at words[at] runs, past its options, their values, its
    assignments and the words that come before the program; the index of its option among `strings` whose value is a
    command of its own, or None). The first index is len(words) when it names no program."""
    valued, positional = WRAPPED[program]
    at += 1
    while at < len(words):
        option, given, _ = words[at].partition("=")
        if words[at] == "--":       # its options end; the words before its program do not (timeout -- 60 cmd)
            return min(at + 1 + positional, len(words)), None
        if ASSIGNMENT.match(words[at]):
            at += 1
        elif words[at].startswith("-") and words[at] != "-":
            if option in strings:
                return at, at
            at += 2 if option in valued and not given else 1
        elif positional:
            positional -= 1
            at += 1
        else:
            break
    return at, None


# ---- names the command gives a new meaning: functions, aliases, a path hashed for a name

# A function the command defines: f() { ...; }, or function f { ...; } and zsh's function f g { ...; }, its body opened
# on the same line or the next. A name is read as the shell reads it, its quotes and backslashes taken out: 'git'() and
# \git() define git. It is read in a script with its quoted data masked (_masked), so prose is never a definition.
DEFINES = re.compile(r"(?:^|[\s;&|(){}])function\s+([^{}()<>;&|\n]*?)\s*(?:\(\s*\)\s*)?(?=[{(])|"
                     r"(?:^|[\s;&|(){}])([^\s;&|(){}<>]+)\s*\(\s*\)")
# What a quote holds that the shell would otherwise read as the end of a word or a command.
MASKED = set(" \t\r\n;&|(){}<>`$")
# zsh's tables of them: functions[f]=..., aliases[a]=..., galiases[a]=..., and those it holds disabled.
TABLES = re.compile(r"(?:^|[\s;&|(){}])(?:dis_)?(functions|aliases|galiases)\[['\"]?([^]'\"]*)['\"]?\]\+?=")
# A command substitution that names a program's path: $(which claude), `command -v git` and their like.
WHICH = re.compile(r"(?:\$\(|`)\s*(?:which|command\s+-v|type\s+-p|whence\s+-p)\s+([\w./+-]+)\s*(?:\)|`)")
# A variable set to one: C=$(which claude).
WHICH_INTO = re.compile(r"([A-Za-z_]\w*)=[\"']?(?:\$\(|`)\s*(?:which|command\s+-v|type\s+-p|whence\s+-p)\s+"
                        r"([\w./+-]+)\s*(?:\)|`)")


def _scripts(text: str, spend=None) -> tuple:
    """(the simple commands of `text`, its text and that of each script it runs: sh -c, eval, a substitution), each
    script with its here-documents' bodies left out. Raises ValueError or RecursionError when it cannot be split."""
    texts = []
    found = commands(text, spend, texts)
    return found, [_masked(without_heredocs(script)) for script in texts]


def _masked(script: str) -> str:
    """`script` with its quotes taken out and what they hold made one word: each character that would end a word or a
    command is `_`. A name stays as the shell reads it ('git'() is git()); prose in a commit message is one word, never
    a definition. A comment, from an unquoted # that begins a word (after COMMENTS_AFTER) to its line's end, is left
    out, as commands() leaves it out, so an apostrophe in it holds nothing (issue 181). A script a quote holds that
    runs (sh -c '...', eval, "$(...)") is read as a script of its own."""
    out, quote, i = [], None, 0
    while i < len(script):
        c = script[i]
        if quote is None and c == "\\" and i + 1 < len(script):
            out.append(script[i:i + 2])
            i += 2
            continue
        if quote is None and c == "#" and (i == 0 or script[i - 1] in COMMENTS_AFTER):
            end = script.find("\n", i)
            i = len(script) if end < 0 else end
            continue
        if quote is None and c in "'\"":
            quote = c
        elif quote is not None and c == quote:
            quote = None
        elif quote is not None:
            if quote == '"' and c == "\\" and i + 1 < len(script):
                i += 1
                c = script[i]
            out.append("_" if c in MASKED else c)
        else:
            out.append(c)
        i += 1
    return "".join(out)


def functions(text: str, spend=None) -> set:
    """The names the command defines as a function: in its text, and in each script it runs (sh -c, eval, a command
    substitution), so a quote around a script hides none; zsh's functions[f]= among them. Raises ValueError or
    RecursionError when the text cannot be split."""
    names = set()
    if "(" not in text and "function" not in text:
        return names        # each definition holds one or the other, and a script it runs is made of its text
    for script in _scripts(text, spend)[1]:
        for listed, single in DEFINES.findall(script):
            names |= {_unquoted(name) for name in (listed.split() if listed else [single])}
        names |= {name for table, name in TABLES.findall(script) if table == "functions"}
    return names


def _unquoted(name: str) -> str:
    """A name as the shell reads it: its quotes and backslashes taken out."""
    return re.sub(r"[\\'\"]", "", name)


def aliases(words: list) -> list:
    """(name, value) of each alias one simple command defines: alias NAME=VALUE, past a prefix (builtin alias), its
    options (zsh's -g, -s) left out."""
    _, command, args = _leading(words)
    if command != "alias":
        return []
    return [tuple(w.split("=", 1)) for w in args if "=" in w[1:] and not w.startswith("-")]


def defined(text: str, spend=None) -> set:
    """Every name the command may give a new meaning, so that it runs another program than the one on PATH: a function
    or an alias, in its text or in a script it runs, zsh's tables of them among them; a path hashed for a name (hash -p
    PATH NAME, zsh's hash NAME=PATH); a built-in loaded or enabled (enable); a function loaded or declared by name
    (autoload, functions, typeset -f, declare -f). Raises ValueError or RecursionError when the text cannot be split."""
    found, texts = _scripts(text, spend)
    names = functions(text, spend)
    for script in texts:
        names |= {name for _, name in TABLES.findall(script)}
    for words, _ in found:
        names |= {name for name, _ in aliases(words)}
        _, command, args = _leading(words)
        if command in ("hash", "enable"):
            names |= {w.split("=", 1)[0] for w in args if not w.startswith("-")}
        # A name given to autoload or functions, or to typeset or declare with -f, is loaded or defined (issue 181).
        if command in LOADERS or (command in ("typeset", "declare") and any(DECLARES_F.match(a) for a in args)):
            names |= {_unquoted(w) for w in args if not w.startswith(("-", "+"))}
    return names


# The built-ins that load a function by name: zsh's and ksh's autoload, and zsh's functions (functions -u NAME).
LOADERS = ("autoload", "functions")
DECLARES_F = re.compile(r"^[-+]\w*f")


# zsh's table of aliases, as a word the shell runs: aliases[g]=git, its key quoted or not, and those it holds disabled.
TABLE_ALIAS = re.compile(r"^(?:dis_)?g?aliases\[([^]]*)\]\+?=(.*)$", re.S)


def expands(code: str) -> bool:
    """Whether `code`, read as the shell reads it, expands a variable or a command: a `$` or a backtick that no
    backslash escapes and no single quote holds. `echo \\$HOME` and 'echo $HOME' expand nothing."""
    quote, i = None, 0
    while i < len(code):
        c = code[i]
        if quote == "'":
            quote = None if c == "'" else quote
        elif c == "\\":
            i += 2
            continue
        elif c in "$`":
            return True
        elif c == '"':
            quote = None if quote == '"' else '"'
        elif c == "'" and quote is None:
            quote = "'"
        i += 1
    return False


def alias_values(text: str, spend=None) -> dict:
    """{name: [the text of each value it is given, an empty one too, and None where it is unaliased]} of each alias the
    command defines whose value the hook can read, as aliased reads them, so that a hook can read the alias's text in
    place of its name where it runs, as the shell expands it (decision 0032, issue 174). The order the shell defines
    them in is not kept: a name given more than one value, or unaliased, is read as each wherever it runs."""
    values = {}
    aliased(text, set(), spend, values)
    for words, _ in commands(text, spend):
        _, command, args = _leading(words)
        if command == "unalias":
            names = list(values) if "-a" in args else [_unquoted(w) for w in args if not w.startswith("-")]
            for name in names:
                if name in values and None not in values[name]:
                    values[name].append(None)
    for name, each in values.items():
        if len(each) > 1 and None not in each:
            each.append(None)       # before its first definition, too, the name is itself
    return values


def aliased(text: str, names: set, spend=None, values: dict = None) -> set:
    """The names the command makes an alias for a value that runs one of `names`: a value that holds one of them as a
    word (by its base name: /usr/bin/git is git), in its text or in a script it runs, by alias or zsh's aliases[g]=,
    as the words the shell runs give them; or a value the hook cannot read, which expands a variable or a command, or
    cannot be split. An alias's value is code, so `alias g=git` then `g push` on a later line is a push. Prose that says
    alias g=git, in a commit message or given to any other program, defines nothing. Raises ValueError or
    RecursionError when the text cannot be split."""
    found = set()
    # A $ or a backtick a backslash held in double quotes stays escaped in the value, so that it expands nothing there
    # (decision 0030).
    escaped = {ord(mark): "\\" + c for c, mark in ESCAPED.items()}
    for words, _ in commands(text, spend, marked=True):
        words = [unmarked(w.translate(escaped)) for w in words]
        at = 0      # zsh's table is set where an assignment stands, before the command: anywhere else it is a word
        while at < len(words) and (ASSIGNMENT.match(words[at]) or TABLE_ALIAS.match(words[at])):
            at += 1
        given = aliases(words) + [(m.group(1), m.group(2)) for m in map(TABLE_ALIAS.match, words[:at]) if m]
        for name, value in given:
            if expands(value):
                found.add(_unquoted(name))
                continue
            try:
                read = commands(value, spend)
            except ValueError:
                found.add(_unquoted(name))
                continue
            if values is not None:      # `values`, if given, gets the text of each value that can be read, '' too
                values.setdefault(_unquoted(name), []).append(value)
            if {os.path.basename(_unquoted(w)) for inner, _ in read for w in inner} & names:
                found.add(_unquoted(name))
    return found


# The built-ins that write or export a variable a word names, and env, which sets one for the program it runs.
SETTERS = {"export", "declare", "typeset", "local", "readonly", "read", "mapfile", "readarray", "printf", "getopts",
           "unset", "let", "env"}


def sets(name, text: str, spend=None) -> bool:
    """Whether the command may set the variable `name`, or any of a set of names given in its place, read in one pass
    from the words the shell runs, in its text and in each script it runs: an assignment before a command, alone, or
    given to a wrapper (NAME=, NAME+=, NAME[i]=); the name given to a built-in that writes or exports it (export,
    declare, read, printf -v, unset and the like); a for or a select over it; and ${NAME:=v} or arithmetic anywhere. A
    quoted word given to any other program is data: a commit message that says NAME= sets nothing. Raises ValueError
    or RecursionError when the text cannot be split."""
    names = {name} if isinstance(name, str) else set(name)
    if names & assigned_elsewhere(text):
        return True
    assigns = re.compile(r"^(?:%s)(?:\[[^]]*\])?\+?=" % "|".join(map(re.escape, sorted(names))))
    for words, _ in commands(text, spend):
        if words[:1] in (["for"], ["select"]) and words[1:2] and words[1] in names:
            return True
        at = 0
        while at < len(words):
            word = words[at]
            if assigns.match(word):
                return True
            command = os.path.basename(word)
            if ASSIGNMENT.match(word) or word in PREFIXES:
                at += 1
            elif command in SETTERS:
                given = _printf_targets(words[at + 1:]) if command == "printf" else words[at + 1:]
                if any(assigns.match(w) or w in names for w in given):
                    return True
                break       # this command sets other names: a later one may set this
            elif command in WRAPPED:
                past = past_wrapper(words, at, command)[0]
                if any(assigns.match(w) for w in words[at + 1:past]):
                    return True
                at = past
            else:
                break
    return False


def _printf_targets(args: list) -> list:
    """The names printf is given to write into, by -v NAME or -vNAME among its options, a subscript taken off; every
    other word printf is given is text it prints, never a name it sets (issue 181)."""
    names, i = [], 0
    while i < len(args) and args[i].startswith("-") and args[i] != "--":
        if args[i] == "-v" and i + 1 < len(args):
            names.append(args[i + 1])
            i += 1
        elif args[i].startswith("-v"):
            names.append(args[i][2:])
        i += 1
    return [re.sub(r"\[.*\]$", "", name) for name in names]      # PATH[1] is PATH, as an assignment's subscript is


def set_anywhere(name: str, text: str) -> bool:
    """Whether the command may set the variable `name` anywhere, read as text: NAME=, NAME+=, ${NAME:=}, NAME[i]=, or
    the name given to a built-in that writes or exports it (read, printf -v, export, declare and the like), in a
    script, a subshell or a condition as much as at the top level."""
    return re.search(r"(?<![\w-])%s(?:\[[^]]*\])?\+?:?=|\b(?:read|printf|getopts|mapfile|readarray|declare|typeset|"
                     r"local|export|readonly|let)\b[^;&|\n]*(?<![\w-])%s(?![\w-])" % (re.escape(name), re.escape(name)),
                     text) is not None
