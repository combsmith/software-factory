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


def commands(text: str, spend=None, texts: list = None) -> list:
    """Each simple command in `text`, as (words, [(operator, target)]), read as simple_commands reads it.

    An operator holding '>' writes its target; one holding only '<' reads it. `spend`, if given, is called
    before each script is read, and may raise to stop a reading that has run over its budget. `texts`, if
    given, gets each script read: `text`, and every script it runs (sh -c, eval, a command substitution).
    """
    if spend:
        spend()
    if texts is not None:
        texts.append(text)
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
        out += _inner(words, spend, texts)
        for word in words:
            for script in _substituted(word):
                out += commands(script, spend, texts)
    return [(words, targets) for words, targets in out if words or targets]


def _inner(words: list, spend=None, texts: list = None) -> list:
    """The commands of a script run by this one: `bash -c '...'` or `eval ...`, also after env, xargs or sudo; and
    the command string of `flock -c`, `script -c`, `runuser -c`, `su -c` and `env -S`."""
    for at, word in enumerate(words):
        name = os.path.basename(word)
        if name == "eval":
            return commands(" ".join(words[at + 1:]), spend, texts)
        if name == "env":       # -S's string is split into the words of the command env runs, before the rest
            for i in range(at + 1, len(words)):
                if not words[i].startswith("-") and "=" not in words[i] and words[i - 1] not in ENV_VALUED:
                    break       # the program env runs: what follows is its own
                script, taken = _value(words, i, "S", ("--split-string",), True)
                if script is not None:
                    rest = words[i + 1 + taken:]
                    return commands(" ".join([script] + [shlex.quote(w) for w in rest]), spend, texts)
        if name in SHELLS or name in STRINGS:
            script = script_of(words, at)
            return [] if script is None else commands(script, spend, texts)
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
    """`text` split into its top-level segments, each (words, before, after, start): the connectors that bound it
    and where it starts in `without_heredocs(text)`. Raises ValueError when a here-document is never ended.

    A here-document's body is data and is left out first. A segment is the run between top-level `;`, newline,
    `&&`, `||`, `|` and `&`; a newline right after `&&`, `||` or `|` continues the list, as the shell reads it.
    Quotes (`$'...'` with its escapes too), `( )`, `$( )`, `${ }` and backticks are opaque, so a separator inside
    one does not split, and a backslash before a newline joins the lines. Each segment's words are built as the
    shell would: quotes are removed, but a command substitution, a parameter expansion or a subshell inside a word
    is kept whole, so an assignment's value can be told apart from a command it runs.
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
            if c == ("'" if quote == "ansi" else quote):
                quote = None
            elif c == "\\" and quote in ('"', "ansi") and i + 1 < len(text):
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
        if text.startswith("$'", i):
            quote, started = "ansi", True       # $'...': a backslash escapes, \' among them
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
    bad |= set(re.findall(r"(?:^|[\s;&|(){}`])(%s)\[" % NAME, stripped))      # X[0]=, an array
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
        if trusted and not GIT_OR_GH.search(stripped[:start]):
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
# The prefixes and wrappers a commit or a push may run under (decision 0023): each runs the program its words name as
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
        elif word == "function":
            at += 2
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
        if words[at] == "--":
            return at + 1, None
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

# A function the command defines: f() { ...; } or function f { ...; }.
DEFINES = re.compile(r"(?:^|[\s;&|(){}])function\s+([A-Za-z_][\w.-]*)|"
                     r"(?:^|[\s;&|(){}])([A-Za-z_][\w.-]*)\s*\(\s*\)")
# zsh's tables of them: functions[f]=..., aliases[a]=..., galiases[a]=..., and those it holds disabled.
TABLES = re.compile(r"(?:^|[\s;&|(){}])(?:dis_)?(functions|aliases|galiases)\[['\"]?([^]'\"]*)['\"]?\]\+?=")
# A command substitution that names a program's path: $(which claude), `command -v git` and their like.
WHICH = re.compile(r"(?:\$\(|`)\s*(?:which|command\s+-v|type\s+-p|whence\s+-p)\s+([^\s)`'\"]+)\s*(?:\)|`)")
# A variable set to one: C=$(which claude).
WHICH_INTO = re.compile(r"([A-Za-z_]\w*)=[\"']?(?:\$\(|`)\s*(?:which|command\s+-v|type\s+-p|whence\s+-p)\s+"
                        r"([^\s)`'\"]+)")


def _scripts(text: str, spend=None) -> tuple:
    """(the simple commands of `text`, its text and that of each script it runs: sh -c, eval, a substitution), each
    script with its here-documents' bodies left out. Raises ValueError or RecursionError when it cannot be split."""
    texts = []
    found = commands(text, spend, texts)
    return found, [without_heredocs(script) for script in texts]


def functions(text: str, spend=None) -> set:
    """The names the command defines as a function: in its text, and in each script it runs (sh -c, eval, a command
    substitution), so a quote around a script hides none; zsh's functions[f]= among them. Raises ValueError or
    RecursionError when the text cannot be split."""
    names = set()
    for script in _scripts(text, spend)[1]:
        names |= {a or b for a, b in DEFINES.findall(script)}
        names |= {name for table, name in TABLES.findall(script) if table == "functions"}
    return names


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
    PATH NAME, zsh's hash NAME=PATH); a built-in loaded or enabled (enable). Raises ValueError or RecursionError when
    the text cannot be split."""
    found, texts = _scripts(text, spend)
    names = functions(text, spend)
    for script in texts:
        names |= {name for _, name in TABLES.findall(script)}
    for words, _ in found:
        names |= {name for name, _ in aliases(words)}
        _, command, args = _leading(words)
        if command in ("hash", "enable"):
            names |= {w.split("=", 1)[0] for w in args if not w.startswith("-")}
    return names


def set_anywhere(name: str, text: str) -> bool:
    """Whether the command may set the variable `name` anywhere, read as text: NAME=, NAME+=, ${NAME:=}, NAME[i]=, or
    the name given to a built-in that writes or exports it (read, printf -v, export, declare and the like), in a
    script, a subshell or a condition as much as at the top level."""
    return re.search(r"(?<![\w-])%s(?:\[[^]]*\])?\+?:?=|\b(?:read|printf|getopts|mapfile|readarray|declare|typeset|"
                     r"local|export|readonly|let)\b[^;&|\n]*(?<![\w-])%s(?![\w-])" % (re.escape(name), re.escape(name)),
                     text) is not None
