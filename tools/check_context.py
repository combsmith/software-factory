"""The context an author builds from is part of the product, and is checked like the rest.

Every rule written for an author names the check that holds it. A rule whose
check cannot exist yet says what it is `waiting on`; once that path exists,
this check fails until the rule names a real one. A path in backticks is a
path in this repo, and must exist.
"""
from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
ROOT_LINES = 60     # the root AGENTS.md is read in full on every task
LOCAL_LINES = 40    # a directory's AGENTS.md carries that directory's rules only
PAGE_LINES = 120    # a standard is one page
STANDARDS = ("code", "tests", "workflows", "security-boundaries")
SKIP = {".git", "__pycache__", "corpus"}
# The design, brought in as it was written. It cites the proof of concept as evidence, by that
# repo's paths and numbers, so it is read and not held to the rules below. Nothing else is exempt.
RECORD = ("docs/prd", "docs/architecture", "docs/research")
# The parts not built yet. A rule may wait only on one of these, so that no wait can be forgotten.
PLANNED = ("adapters", "harness", "controller", "roles", "release", "evals", ".github")

TOKEN = re.compile(r"`([^`\n]+)`")
PATHLIKE = re.compile(r"^[\w.-]+(/[\w.-]+)*/?$")
SUFFIXES = (".py", ".json", ".md", ".yml", ".yaml")
WAITING = re.compile(r"waiting on `([^`\n]+)`")
MODULE = re.compile(r"python3 -m ([\w.]+)")
BARE_NUMBER = re.compile(r"(?<![\w/&`])#\d+\b")
DATE = re.compile(r"\b20\d\d-\d\d-\d\d\b")
NUMBERED = re.compile(r"\b(?:issue|pull request)(?: number)? \d+\b", re.I)


def _markdown(root: pathlib.Path) -> list:
    """The files an author is told to read: every AGENTS.md, and everything under docs/."""
    found = [p for p in root.rglob("*.md") if not SKIP & set(p.relative_to(root).parts)]
    found = [p for p in found if not p.relative_to(root).as_posix().startswith(RECORD)]
    return sorted(p for p in found if p.name == "AGENTS.md" or "docs" in p.relative_to(root).parts)


def _named(text: str, root: pathlib.Path, here: pathlib.Path) -> list:
    """(path, test name, exists) for each backticked token that claims to be a path here."""
    top = {p.name for p in root.iterdir()}
    out = []
    for token in TOKEN.findall(text):
        name, _, test = token.partition("::")
        if not PATHLIKE.match(name):
            continue
        claims = name.split("/")[0] in top or name.endswith(SUFFIXES)
        if not claims:
            continue
        target = root / name if (root / name).exists() else here / name
        ok = target.exists()
        if ok and test:
            ok = ("def %s(" % test.split(".")[-1]) in target.read_text()
        out.append((token, ok))
    return out


def _held(cell: str, where: str, root: pathlib.Path, here: pathlib.Path) -> list:
    """A rule's check is a path that exists, or a path it is waiting on that does not exist yet."""
    problems = []
    waits = WAITING.findall(cell)
    for path in waits:
        if path.split("/")[0] not in PLANNED:
            problems.append("%s: waits on %s, which is not a planned part of this repo" % (where, path))
        elif (root / path).exists():
            problems.append("%s: %s exists now; name the check that holds this rule" % (where, path))
    if not waits and not _named(cell, root, here):
        problems.append("%s: names no check" % where)
    return problems


def _sections(text: str, mark: str) -> list:
    """(heading, body) for each section that opens with `mark`, up to the next heading of that depth or less."""
    out, head, body = [], None, []
    depth, fenced = len(mark.strip()), False
    for line in text.splitlines():
        hashes = len(line) - len(line.lstrip("#"))
        if line.startswith("```"):
            fenced = not fenced
        if fenced:
            hashes = 0      # a comment inside an example is not a heading
        if hashes and line.startswith(mark):
            if head is not None:
                out.append((head, "\n".join(body)))
            head, body = line[len(mark):].strip(), []
        elif head is not None and 0 < hashes <= depth and line[hashes:hashes + 1] == " ":
            out.append((head, "\n".join(body)))
            head, body = None, []
        elif head is not None:
            body.append(line)
    if head is not None:
        out.append((head, "\n".join(body)))
    return out


def _rows(body: str) -> list:
    """The cells of each row of the first table in `body`, without its header."""
    rows = [ln for ln in body.splitlines() if ln.startswith("|")]
    return [[c.strip() for c in ln.strip("|").split("|")] for ln in rows[2:]]


def _references(path: pathlib.Path, text: str, root: pathlib.Path) -> list:
    rel = path.relative_to(root)
    problems = []
    for token, ok in _named(WAITING.sub("", text), root, path.parent):
        if not ok:
            problems.append("%s: names %s, which is not in this repo" % (rel, token))
    for module in MODULE.findall(text):
        if not (root / (module.replace(".", "/") + ".py")).exists():
            problems.append("%s: runs %s, which is not in this repo" % (rel, module))
    if BARE_NUMBER.search(text):
        problems.append("%s: a bare issue or pull-request number; give its title" % rel)
    for block in re.split(r"\n\s*\n", text):
        for part in (block.splitlines() if block.lstrip().startswith("|") else [block]):
            if NUMBERED.search(part) and '"' not in part:
                problems.append("%s: an issue or pull request is numbered without its title" % rel)
    return problems


def _agents_files(root: pathlib.Path) -> list:
    problems = []
    main = root / "AGENTS.md"
    lines = main.read_text().splitlines()
    if len(lines) > ROOT_LINES:
        problems.append("AGENTS.md is %d lines; the limit is %d. Move detail to a directory or to docs/"
                        % (len(lines), ROOT_LINES))
    for path in sorted(p for p in root.rglob("AGENTS.md") if not SKIP & set(p.relative_to(root).parts)):
        if DATE.search(path.read_text()):
            problems.append("%s holds a date; what is read on every task does not change with the day"
                            % path.relative_to(root))
    entry = root / "CLAUDE.md"
    if not entry.exists() or entry.read_text().strip() != "@AGENTS.md":
        problems.append("CLAUDE.md must hold the one line @AGENTS.md, so that there is one set of rules")
    if "| Held by |" not in main.read_text():
        problems.append("AGENTS.md: no table of rules and the checks that hold them")
    for path in sorted(p for p in root.rglob("AGENTS.md") if not SKIP & set(p.relative_to(root).parts)):
        table = []
        for line in path.read_text().splitlines() + [""]:
            if line.startswith("|"):
                table.append([c.strip() for c in line.strip("|").split("|")])
                continue
            if table and table[0][-1] == "Held by":
                for cells in table[2:]:
                    where = "%s, rule '%s'" % (path.relative_to(root), cells[0][:50])
                    problems += _held(cells[-1], where, root, path.parent)
            table = []
    for folder in sorted(p for p in root.iterdir() if p.is_dir() and p.name not in SKIP
                         and not p.name.startswith(".")):
        local = folder / "AGENTS.md"
        if not local.exists():
            problems.append("%s/ has no AGENTS.md" % folder.name)
        elif len(local.read_text().splitlines()) > LOCAL_LINES:
            problems.append("%s/AGENTS.md is over %d lines" % (folder.name, LOCAL_LINES))
    return problems


def _decisions(root: pathlib.Path) -> list:
    problems = []
    records = sorted((root / "docs" / "decisions").glob("[0-9]*.md"))
    if not records:
        return ["docs/decisions/ holds no record"]
    for want, path in enumerate(records, 1):
        text = path.read_text()
        if not path.name.startswith("%04d-" % want):
            problems.append("docs/decisions/%s: records are numbered from 0001 with no gap" % path.name)
        if not text.startswith("# %04d. " % want):
            problems.append("docs/decisions/%s: the title must open with its number" % path.name)
        parts = dict(_sections(text, "## "))
        for need in ("Decision", "Why", "Boundaries"):
            if not parts.get(need, "").strip():
                problems.append("docs/decisions/%s: no section %s" % (path.name, need))
        rows = _rows(parts.get("Boundaries", ""))
        if not rows:
            problems.append("docs/decisions/%s: names no boundary a check can assert" % path.name)
        for i, cells in enumerate(rows, 1):
            problems += _held(cells[-1], "docs/decisions/%s, boundary %d" % (path.name, i), root, path.parent)
    return problems


def _lessons(root: pathlib.Path) -> list:
    path = root / "docs" / "lessons.md"
    if not path.exists():
        return ["docs/lessons.md is missing"]
    problems, seen = [], set()
    lessons = [(h, b) for h, b in _sections(path.read_text(), "### ") if re.match(r"L-\d+\b", h)]
    if not lessons:
        problems.append("docs/lessons.md holds no lesson")
    for head, body in lessons:
        tag = head.split()[0].rstrip(".")
        if tag in seen:
            problems.append("docs/lessons.md: %s is used twice" % tag)
        seen.add(tag)
        fields = {}
        for line in body.splitlines():
            for name in ("Failure", "Rule", "Check"):
                if line.startswith("**%s.**" % name):
                    fields[name] = line
        for name in ("Failure", "Rule", "Check"):
            if name not in fields:
                problems.append("docs/lessons.md: %s has no %s" % (tag, name))
        if "Check" in fields:
            problems += _held(fields["Check"], "docs/lessons.md, %s" % tag, root, path.parent)
    return problems


def _standards(root: pathlib.Path) -> list:
    problems = []
    folder = root / "docs" / "standards"
    for name in STANDARDS:
        path = folder / (name + ".md")
        if not path.exists():
            problems.append("docs/standards/%s.md is missing" % name)
            continue
        text = path.read_text()
        if len(text.splitlines()) > PAGE_LINES:
            problems.append("docs/standards/%s.md is over one page (%d lines)" % (name, PAGE_LINES))
        sections = _sections(text, "## ")
        if not sections:
            problems.append("docs/standards/%s.md states no rule" % name)
        for head, body in sections:
            where = "docs/standards/%s.md, '%s'" % (name, head)
            held = [ln for ln in body.splitlines() if ln.startswith("Held by:")]
            if not held:
                problems.append("%s: no 'Held by:' line" % where)
                continue
            if "```" not in body.split("Held by:")[0]:
                problems.append("%s: the example comes before the prose, and there is none" % where)
            problems += _held(held[0], where, root, folder)
    # The review standard is the rubric, as data. A page here would be a second copy.
    for path in sorted(folder.glob("*review*")) if folder.exists() else []:
        problems.append("docs/standards/%s: the review standard is config/rubric-pr-review.json" % path.name)
    return problems


def run(root: pathlib.Path = ROOT) -> list:
    problems = []
    for path in _markdown(root):
        problems += _references(path, path.read_text(), root)
    return problems + _agents_files(root) + _decisions(root) + _lessons(root) + _standards(root)
