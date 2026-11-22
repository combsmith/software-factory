"""A Release's notes: the squash subjects merged since the Release before it, grouped by area (issue 1093).

Since 2026-11-21 a pull request's title is `area: plain verb phrase (#issue)`, and the squash commit's subject is
that title with GitHub's ` (#PR)` after it, so the subjects between two Release tags read as change notes. Each subject
in that form is listed under its area, areas in the order of their names, each area's changes in the order they merged;
a subject in no such form, from before the style or made by something else, is listed as it is, under its own heading.
A subject's text is shown literally: no markup in it renders and no mention in it notifies. `notes` is given the
subjects and reads nothing; `main` reads them from stdin, one to a line as git prints them. A cut has at least one
commit, so no subjects is a history that was not read, and refuses.

It runs after a cut's read-back, in the one line the skill `.claude/skills/cut-a-release/SKILL.md` prints, which
publishes nothing unless every step before it succeeded.
"""
from __future__ import annotations

import re
import sys

from release import current

# A squash subject in the plain form: its area, its phrase with its issue, and the pull request GitHub adds.
PLAIN = re.compile(r"(?P<area>[a-z0-9.][a-z0-9._/-]*): (?P<change>\S(?:.*\S)? \(#[1-9][0-9]*(?:, part [0-9]+ of [0-9]+)?\))"
                   r" \(#(?P<pull>[1-9][0-9]*)\)")
OTHER = "Other changes"
# What GitHub's Markdown would read as markup in a subject, each shown as itself; and a mention, which would notify.
MARKUP = re.compile(r"([\\`*_<>\[\]~|!&])")
# What would open a block at a line's start, a heading, a quote, a list item or a rule, its first character escaped.
BLOCK = re.compile(r"^([ \t]*)([-+=>#])")
ORDERED = re.compile(r"^([ \t]*[0-9]+)([.)])")
MENTION = re.compile(r"@(?=[A-Za-z0-9])")
BREAKS = ("\r", "\n", "\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029")


def literal(text: str) -> str:
    """`text` as GitHub's Markdown shows it, character for character: markup and a block's opening escaped, no
    character reference read, and no mention."""
    return ORDERED.sub(r"\1\\\2", BLOCK.sub(r"\1\\\2", MENTION.sub("@\u2060", MARKUP.sub(r"\\\1", text))))


def notes(subjects: list, release: str, previous: str) -> str:
    """The notes of `release`, cut after `previous`, from the squash subjects between them, oldest first. Raises
    ValueError where either is not a Release's name, or a subject is not one line of text."""
    if not current.version(release) or not current.version(previous):
        raise ValueError("both names must be Releases, factory/vMAJOR.MINOR.PATCH")
    if not subjects:
        raise ValueError("no subject was given; a cut has at least one commit, so its history was not read")
    areas, other = {}, []
    for subject in subjects:
        if not isinstance(subject, str) or not subject.strip() or any(b in subject for b in BREAKS):
            raise ValueError("a subject is one line of text")
        plain = PLAIN.fullmatch(subject.strip())
        if plain:
            areas.setdefault(plain.group("area"), []).append("%s (#%s)" % (literal(plain.group("change")), plain.group("pull")))
        else:
            other.append(literal(subject.strip()))
    count = len(subjects)
    lines = ["## %s" % release, "", "%d change%s since %s." % (count, "" if count == 1 else "s", previous)]
    for area in sorted(areas):
        lines += ["", "### %s" % literal(area), ""] + ["- %s" % change for change in areas[area]]
    if other:
        lines += ["", "### %s" % OTHER, ""] + ["- %s" % subject for subject in other]
    return "\n".join(lines) + "\n"


def main(argv=None, stdin=None) -> int:
    """Print the notes of NEW, cut after PREVIOUS, from the squash subjects on stdin, one to a line, oldest first. What
    goes wrong is said on stderr, never in the notes, and the exit is not 0."""
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print("usage: python3 -m release.notes NEW PREVIOUS < subjects", file=sys.stderr)
        return 2
    subjects = [line for line in (sys.stdin if stdin is None else stdin).read().split("\n") if line.strip()]
    try:
        print(notes(subjects, args[0], args[1]), end="")
    except ValueError as err:
        print("release notes: %s" % err, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
