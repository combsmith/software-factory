"""A Release's notes: the squash subjects merged since the Release before it, grouped by area (issue 1093).

Since 2026-11-21 a pull request's title is `area: plain verb phrase (#issue)`, and the squash commit's subject is
that title with GitHub's ` (#PR)` after it, so the subjects between two Release tags read as change notes. Each subject
in that form is listed under its area, areas in the order of their names, each area's changes in the order they merged;
a subject in no such form, from before the style or made by something else, is listed as it is, under its own heading.
Pure: it is given the subjects, and reads nothing.

At the desk, after a cut's read-back (the skill `.claude/skills/cut-a-release/SKILL.md`):
`git log --reverse --format=%s PREVIOUS..NEW | python3 -m release.notes NEW PREVIOUS > notes.md`
"""
from __future__ import annotations

import re
import sys

from release import current

# A squash subject in the plain form: its area, its phrase with its issue, and the pull request GitHub adds.
PLAIN = re.compile(r"(?P<area>[a-z0-9.][a-z0-9._/-]*): (?P<change>\S.*\(#[1-9][0-9]*(?:, part [0-9]+ of [0-9]+)?\))"
                   r" \(#(?P<pull>[1-9][0-9]*)\)")
OTHER = "Other changes"


def notes(subjects: list, release: str, previous: str) -> str:
    """The notes of `release`, cut after `previous`, from the squash subjects between them, oldest first. Raises
    ValueError where either is not a Release's name, or a subject is not one line of text."""
    if not current.version(release) or not current.version(previous):
        raise ValueError("both names must be Releases, factory/vMAJOR.MINOR.PATCH")
    areas, other = {}, []
    for subject in subjects:
        if not isinstance(subject, str) or not subject.strip() or "\n" in subject:
            raise ValueError("a subject is one line of text")
        plain = PLAIN.fullmatch(subject.strip())
        if plain:
            areas.setdefault(plain.group("area"), []).append("%s (#%s)" % (plain.group("change"), plain.group("pull")))
        else:
            other.append(subject.strip())
    count = sum(len(changes) for changes in areas.values()) + len(other)
    lines = ["## %s" % release, "", "%d change%s since %s." % (count, "" if count == 1 else "s", previous)]
    for area in sorted(areas):
        lines += ["", "### %s" % area, ""] + ["- %s" % change for change in areas[area]]
    if other:
        lines += ["", "### %s" % OTHER, ""] + ["- %s" % subject for subject in other]
    return "\n".join(lines) + "\n"


def main(argv=None, stdin=None) -> int:
    """Print the notes of NEW, cut after PREVIOUS, from the squash subjects on stdin, oldest first."""
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print("usage: git log --reverse --format=%s PREVIOUS..NEW | python3 -m release.notes NEW PREVIOUS")
        return 2
    subjects = [line for line in (sys.stdin if stdin is None else stdin).read().splitlines() if line.strip()]
    try:
        print(notes(subjects, args[0], args[1]), end="")
    except ValueError as err:
        print("release notes: %s" % err)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
