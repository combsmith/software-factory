"""A pull request's title is `area: plain verb phrase (#issue)`, in at most LONGEST characters (issue 1089).

The squash commit takes the title as its subject, so what a pull request is called is main's log for good. The
`commits` job of the required check calls `check` through `commits_are_the_maintainers.py`, from the base, so a change
cannot make its own title pass (decision 0244). `check` reads the title from GitHub, never from the event's payload, so
a title edited before review is read again when the failed job is re-run; on a merge group it reads the pull request the
queue's ref names, as it is when it merges. A title that cannot be read refuses.

Only the mechanical half of the rule is held here: the length, the area, a phrase that starts with a lowercase letter
and ends with no stop, the issue and the part's numbers, and the marks of a name from inside the code. Whether a title
names one change, and in words a newcomer can read, is judgment: the reviewers'. A pull request opened before CUTOVER
is not read. The title is text from outside: what this prints names a rule's code and a position, never a word of the
title, so no title can write a command into a job's log.

The body is held to the template's shape (decision 0246): `.github/pull_request_template.md`'s four headings, each once,
in that order, each over some text. A heading inside a code fence is no heading, and the template's own scaffolding (a
comment, an empty list item, the checks-and-readers block) is no text.
What the body says is the reviewers' to judge. A pull request opened before BODY_CUTOVER is not read for its body.

Run `python3 -m tools.pr_title "TITLE"`, and `python3 -m tools.pr_title --body FILE`, at the desk before opening a pull
request.
"""
from __future__ import annotations

import datetime
import json
import pathlib
import re
import sys

from adapters.github import Live, Unanswered, request

LONGEST = 72                        # characters; the Maintainer's "about 70". GitHub's " (#N)" on the squash is not counted
CUTOVER = "2026-11-22T00:00:00Z"    # a pull request opened before this is not read (issue 1089)
BODY_CUTOVER = "2026-11-23T00:00:00Z"   # nor, for its body, one opened before this (decision 0246)
# The body's headings, from .github/pull_request_template.md, in their order.
HEADINGS = ("Why", "What changed", "What to look at", "Record and protected edits")
# A code fence: three or more backticks or tildes, after any indent or list marker, so that a fence in a list item hides
# what it holds too (reading an indented fence as one only hides more); it closes on its own kind, at least as long,
# at most three columns further in than its list item, with nothing but spaces or tabs after it. A backtick fence's words
# hold no backtick, or it is inline code. It opens only on a line that starts outside the scaffolding, read as written.
# NOSONAR below: a false positive, confirmed (issue 1196). Each list marker must start its group and a fence ends
# the pattern, which is matched whole on one line: 8,000 markers with no fence take under a millisecond.
FENCE_OPEN = re.compile(r"[ \t]*(?:(?:[-*+]|[0-9]{1,9}[.)])[ \t]+)*(`{3,}|~{3,})([^\n]*)")  # NOSONAR
FENCE_CLOSE = re.compile(r"[ \t]*(`{3,}|~{3,})[ \t]*")
# The template's own scaffolding, which is no text and hides any heading in it: its comments, the checks-and-readers
# block (nested, of any case, with attributes), and an empty list item. A comment or a block left open runs to the end.
DETAILS_OPEN = re.compile(r"<details(?:[ \t][^>\n]{0,200})?>", re.I)
DETAILS_CLOSE = re.compile(r"</details[ \t]*>", re.I)
COMMENT = re.compile(r"<!--")
# Inline code, in which GitHub reads no markup: a run of up to eight backticks, then what it holds, then the same run.
CODE_SPAN = re.compile(r"(?<!`)(`{1,8})(?!`)[^\n]{0,4000}?(?<!`)\1(?!`)")
EMPTY_ITEM = re.compile(r"(?:[-*+]|[0-9]{1,9}[.)])?")   # read on the line stripped of spaces and tabs
AREA = re.compile(r"[a-z0-9.][a-z0-9._/-]*: (?=\S)")
TAIL = re.compile(r" \(#[1-9][0-9]*(?:, part (0|[1-9][0-9]*) of (0|[1-9][0-9]*))?\)\Z")
# The marks of a name from inside the code, which a newcomer cannot read.
INTERNAL = (("a backtick", re.compile(r"`")),
            ("a name joined by an underscore", re.compile(r"[A-Za-z0-9]_[A-Za-z0-9]")),
            ("a record's number", re.compile(r"\b(?:record|decision)s?\s+#?[0-9]{4}\b", re.I)),
            ("a trial's number", re.compile(r"\bP-[0-9]+\b", re.I)),
            ("a schema's name and version", re.compile(r"\b[a-z]+/[0-9]+\b")))
# The queue's ref, as tools/commits_are_the_maintainers.py reads it, whose `queued` also holds its base and its state.
QUEUED = re.compile(r"refs/heads/gh-readonly-queue/[^/]+/pr-([1-9][0-9]*)-[0-9a-f]{40}")
DIGITS = 4                          # a part's number and its count, at most; a longer one is not converted
MOMENT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")


def problems(title: str) -> list:
    """Why `title` breaks the mechanical half of the rule: nothing where it keeps it. No problem holds a word of it."""
    found = []
    if len(title) > LONGEST:
        found.append("title_too_long: the title is %d characters, and the most is %d" % (len(title), LONGEST))
    area = AREA.match(title)
    if area is None:
        found.append("title_no_area: the title does not start with its area, a lowercase word, a colon and a space, "
                     "as in 'kernel: '")
    tail = TAIL.search(title)
    if tail is None:
        found.append("title_no_issue: the title does not end with its issue, as in ' (#123)' or ' (#123, part 1 of 3)'")
    elif tail.group(1) is not None and max(len(tail.group(1)), len(tail.group(2))) > DIGITS:
        found.append("title_part_out_of_range: a part's numbers are longer than %d digits" % DIGITS)
    elif tail.group(1) is not None:
        part, parts = int(tail.group(1)), int(tail.group(2))
        if part < 1 or part > parts or parts < 2:
            found.append("title_part_out_of_range: part %d of %d: a part is at least 1 and at most the count, and the "
                         "count is at least 2" % (part, parts))
    if any(c < " " or c == "\x7f" for c in title):
        found.append("title_control_character: the title holds a tab, a line end or another control character")
    start = area.end() if area else 0
    end = tail.start() if tail else len(title)
    phrase = title[start:end] if end >= start else ""
    if area and not "a" <= phrase[:1] <= "z":
        found.append("title_phrase_not_lowercase: the words after the area, at character %d, do not start with a "
                     "lowercase letter; write a plain verb phrase" % (start + 1))
    if phrase[-1:] in (".", ",", ";", ":") or phrase != phrase.rstrip():
        found.append("title_ends_with_stop: the words end with a stop or a space, at character %d" % end)
    for what, mark in INTERNAL:
        for seen in mark.finditer(title, start):
            found.append("title_internal_term: characters %d to %d hold %s, a name from inside the code; say it in "
                         "plain words" % (seen.start() + 1, seen.end(), what))
    return found


def _heading(line: str):
    """The words of a second-level heading on `line`, as GitHub's Markdown reads one, or None: up to three spaces, `##`,
    then nothing or a space or tab and the words, a closing run of hashes dropped only after a space or tab."""
    indent = len(line) - len(line.lstrip(" "))
    if indent > 3 or not line.startswith("##", indent) or line[indent + 2:indent + 3] not in ("", " ", "\t"):
        return None
    words = line[indent + 2:].strip(" \t")
    closing = len(words) - len(words.rstrip("#"))
    if closing and (closing == len(words) or words[-closing - 1] in " \t"):
        words = words[:-closing].rstrip(" \t")
    return words


def _tag(line: str, at: int, spans: list, pattern):
    """The first match of `pattern` in `line` from `at` that starts outside inline code, or None: `spans` holds, at each
    place in the line, where the code span that holds it ends, or 0."""
    found = pattern.search(line, at)
    while found and spans[found.start()]:
        found = pattern.search(line, spans[found.start()])
    return found


def _visible(line: str, hidden: list) -> str:
    """What of `line` a reader sees outside the scaffolding, `hidden` being [in a comment, details blocks open], which
    it carries from line to line. Outside a comment, a tag or a comment's opening in inline code is none. A tag is
    searched for again only once the reading has passed the one found, so a line is read in about one pass."""
    spans, seen, at, found = [0] * (len(line) + 1), [], 0, {}
    for span in CODE_SPAN.finditer(line):
        spans[span.start():span.end()] = [span.end()] * (span.end() - span.start())
    while at < len(line):
        if hidden[0]:
            end = line.find("-->", at)
            hidden[0], at = (False, end + 3) if end >= 0 else (True, len(line))
            continue
        for pattern in (COMMENT, DETAILS_OPEN, DETAILS_CLOSE):
            if pattern not in found or found[pattern] and found[pattern].start() < at:
                found[pattern] = _tag(line, at, spans, pattern)
        tags = (found[COMMENT], found[DETAILS_OPEN], found[DETAILS_CLOSE] if hidden[1] else None)
        first = min((tag for tag in tags if tag), key=lambda tag: tag.start(), default=None)
        if not hidden[1]:
            seen.append(line[at:first.start() if first else len(line)])
        if first is None:
            break
        at = first.end()
        if first is tags[0]:
            hidden[0] = True
        else:
            hidden[1] += 1 if first is tags[1] else -1
    return "".join(seen)


def body_problems(body: str) -> list:
    """Why `body` is not in the template's shape: nothing where it is. No problem holds a word of it."""
    seen, section, fence, column, hidden = [], None, None, 0, [False, 0]
    for line in body.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if fence is not None:
            closing = FENCE_CLOSE.fullmatch(line)
            indent = len(line[:closing.start(1)].expandtabs(4)) if closing else 0
            if closing and closing.group(1)[0] == fence[0] and len(closing.group(1)) >= len(fence) and indent <= column + 3:
                fence = None
            elif section is not None:
                section[1].append("code" if line.strip() else "")    # a fenced line is text, whatever it holds
            continue
        whole = not hidden[0] and not hidden[1]
        opening = FENCE_OPEN.fullmatch(line) if whole else None
        if opening and not (opening.group(1)[0] == "`" and "`" in opening.group(2)):
            fence, column = opening.group(1), len(line[:opening.start(1)].expandtabs(4))
            column = column if column > 3 or line.lstrip(" \t")[0] not in "`~" else 0
            continue
        visible = _visible(line, hidden)
        words = _heading(line) if whole else None
        if words is not None:
            section = [_visible(words, [False, 0]).strip(" \t"), []]
            seen.append(section)
        elif section is not None:
            section[1].append(visible)
    found, places = [], []
    for name in HEADINGS:
        held = [i for i, (words, _) in enumerate(seen) if words == name]
        if not held:
            found.append("body_heading_missing: the body has no heading '## %s'" % name)
            continue
        if len(held) > 1:
            found.append("body_heading_twice: the body has the heading '## %s' %d times" % (name, len(held)))
        places.append(held[0])
        if any(not any(text.strip() and not EMPTY_ITEM.fullmatch(text.strip(" \t")) for text in seen[i][1]) for i in held):
            found.append("body_section_empty: the section '## %s' holds nothing but the template's own" % name)
    if places != sorted(places):
        found.append("body_heading_out_of_order: the headings are not in the template's order: %s"
                     % ", ".join(HEADINGS))
    return found


def read(environ, transport=None) -> tuple:
    """(the pull request as GitHub answered it, when it was opened, why it cannot be read): the pull request the event
    names, read from GitHub with the job's read-only token. The last is empty where the pull request and when it was
    opened were read; its title and body are held by `check`, since one opened before a cutover needs neither."""
    event, token = environ.get("EVENT"), environ.get("WORKFLOW_TOKEN")
    try:
        payload = json.loads(pathlib.Path(environ["GITHUB_EVENT_PATH"]).read_text())
        if event == "pull_request":
            number = payload["pull_request"]["number"]
        elif event == "merge_group":
            number = int(QUEUED.fullmatch(payload["merge_group"]["head_ref"]).group(1))
        else:
            return None, None, "title_unreadable: EVENT (pull_request or merge_group) must be set from the event"
        repo = payload["repository"]["full_name"]
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as err:
        return None, None, "title_unreadable: the event names no pull request that can be read: %s" % type(err).__name__
    if type(number) is not int or number < 1 or not isinstance(repo, str):
        return None, None, "title_unreadable: the event names no pull request by its number"
    if not token:
        return None, None, "title_unreadable: the job's token was not given"
    try:
        answer = (transport or Live(token)).send(request("GET", "/repos/%s/pulls/%d" % (repo, number)))
    except Unanswered as err:
        return None, None, "title_unreadable: pull request %d was not answered: %s" % (number, type(err).__name__)
    pull = answer.get("body")
    base = pull.get("base") if isinstance(pull, dict) else None
    held = base.get("repo") if isinstance(base, dict) else None
    if answer.get("status") != 200 or not isinstance(pull, dict) or type(pull.get("number")) is not int \
            or pull["number"] != number or not isinstance(held, dict) or held.get("full_name") != repo:
        return None, None, "title_unreadable: pull request %d was answered %s" % (number, answer.get("status"))
    opened = pull.get("created_at")
    try:
        datetime.datetime.strptime(opened if isinstance(opened, str) and MOMENT.fullmatch(opened) else "", "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None, None, "title_unreadable: when pull request %d was opened cannot be read" % number
    return pull, opened, ""


def check(environ, transport=None) -> list:
    """Why the event's pull request's title or body breaks its rule, or cannot be read: nothing where both keep theirs,
    or where the pull request was opened before the cutover of each."""
    pull, opened, why = read(environ, transport)
    if why:
        return [why]
    found = []
    if opened >= CUTOVER:
        title = pull.get("title")
        found += problems(title) if isinstance(title, str) and title else ["title_unreadable: the pull request's title cannot be read"]
    if opened >= BODY_CUTOVER:
        body = pull.get("body")
        found += body_problems(body) if isinstance(body, str) else ["body_unreadable: the pull request's body cannot be read"]
    return found


def main(argv=None) -> int:
    """The desk's check of one title, or of one body's file, before a pull request is opened: its problems, or that it
    keeps the rule."""
    args = sys.argv[1:] if argv is None else argv
    if args[:1] == ["--body"]:
        if len(args) != 2:
            print("usage: python3 -m tools.pr_title --body FILE")
            return 2
        try:
            # NOSONAR on the next line: the desk's own command reads the file its user names, as `cat` would.
            found = body_problems(pathlib.Path(args[1]).read_text(encoding="utf-8"))  # NOSONAR
        except (OSError, ValueError) as err:
            print("body_unreadable: the file cannot be read: %s" % type(err).__name__)
            return 1
        for problem in found:
            print(problem)
        if not found:
            print("the body keeps the template's shape: %s" % ", ".join(HEADINGS))
        return 1 if found else 0
    if len(args) != 1:
        print("usage: python3 -m tools.pr_title \"area: plain verb phrase (#issue)\" | --body FILE")
        return 2
    found = problems(args[0])
    for problem in found:
        print(problem)
    if not found:
        print("the title keeps the rule: area, plain verb phrase, issue, in at most %d characters" % LONGEST)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
