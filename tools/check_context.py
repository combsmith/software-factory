"""The context an author builds from is part of the product, and is checked like the rest.

Every rule written for an author names the check that holds it: a file under one of the places
checks live, or a test in one. A rule whose check cannot exist yet says what it is `waiting on`;
once that part of the repo exists, this check fails until the rule names a real one. A rule that
is decided and not built names a test marked `@pending`, and says `not held yet`. A path in
backticks is a path in this repo, and must exist.
"""
from __future__ import annotations

import pathlib
import re

from tools import walk

ROOT = pathlib.Path(__file__).resolve().parent.parent
ROOT_LINES = 60     # the root AGENTS.md is read in full on every task
LOCAL_LINES = 40    # a directory's AGENTS.md carries that directory's rules only
WIDTH = 260         # and a line is not a way round the limit
PAGE_LINES = 120    # a standard is one page
STANDARDS = ("code", "tests", "workflows", "security-boundaries")
# The design, brought in as it was written. It cites the proof of concept as evidence, by that
# repo's paths and numbers, so it is read and not held to the rules below. Nothing else is exempt.
RECORD = (("docs", "prd"), ("docs", "architecture"), ("docs", "research"))
# The parts not built yet. A rule may wait only on one of these, so that no wait can be forgotten.
PLANNED = ("adapters", "harness", "controller", "roles", "release", "evals", ".github")
# Where a check can live. A document or a file of settings is not a check.
CHECKS = ("tools", "tests", "examples", "schemas", "sim")
# Files other tools load as rules. There is one set of rules, so there are none of these but the
# root CLAUDE.md, which holds one line that imports AGENTS.md.
OTHER_RULES = {"CLAUDE.md", "GEMINI.md", "copilot-instructions.md", ".cursorrules", ".windsurfrules"}
# A procedure done rarely and exactly is a skill: `.claude/skills/<name>/SKILL.md`, loaded when a task
# calls for it. Loading on demand alone was measured as unreliable, so the root file points to each.
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)

TOKEN = re.compile(r"`([^`\n]+)`")
LINK = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")
PATHLIKE = re.compile(r"^[\w.-]+(/[\w.-]+)*/?$")
SUFFIXES = (".py", ".json", ".md", ".yml", ".yaml")
EXTENSION = re.compile(r"\.[a-z0-9]{1,5}$")
PENDING = "not held yet"
WAITING = re.compile(r"waiting on `([^`\n]+)`", re.I)
MODULE = re.compile(r"python3 -m ([\w.]*\w)")
BARE_NUMBER = re.compile(r"(?<![&`])(?<!\]\()#\d+\b")
DATE = re.compile(r"\b20\d\d-\d\d-\d\d\b")
NUMBERED = re.compile(r"\b(?:[Ii]ssue|[Pp]ull request|PR)(?: number)? #?\d+\b")
TITLE = re.compile(r"[\"“][^\"”\n]{8,}[\"”]")


def _text(path: pathlib.Path) -> str:
    return path.read_text(errors="replace")


def _kept(root: pathlib.Path, pattern: str) -> list:
    return [p for p in walk.files(root) if p.match(pattern)]


def _markdown(root: pathlib.Path) -> list:
    """The files an author is told to read: every AGENTS.md, every skill, and everything under docs/ but the record."""
    found = [p for p in _kept(root, "*.md") if p.relative_to(root).parts[:2] not in RECORD]
    return [p for p in found if p.name == "AGENTS.md" or p.relative_to(root).parts[0] == "docs"] + _skill_files(root)


def _skill_files(root: pathlib.Path) -> list:
    folder = root / ".claude" / "skills"
    return sorted(folder.glob("*/SKILL.md")) if folder.is_dir() else []


def _named(text: str, root: pathlib.Path, here: pathlib.Path) -> list:
    """(token, exists, path in the repo) for each backticked token or link that claims to be a path here."""
    top = {p.name for p in root.iterdir()}
    out = []
    for token in TOKEN.findall(text) + [m for m in LINK.findall(text) if "://" not in m and not m.startswith("mailto:")]:
        name, _, test = token.partition("::")
        name = re.sub(r":\d+$", "", name)
        if not PATHLIKE.match(name):
            continue
        first = name.split("/")[0]
        if not (first in top or name.endswith(SUFFIXES) or ("/" in name and EXTENSION.search(name))
                or (name.endswith("/") and first not in PLANNED)):
            continue
        target = root / name if (root / name).exists() else here / name
        ok = target.exists()
        if ok and test:
            parts = test.split(".")
            source = _text(target) if target.is_file() else ""
            ok = re.search(r"(?m)^\s*(async\s+)?def %s\(" % re.escape(parts[-1]), source) is not None and \
                all(re.search(r"(?m)^class %s\b" % re.escape(c), source) for c in parts[:-1])
        rel = target.resolve().relative_to(root.resolve()) if ok else pathlib.PurePath(name)
        out.append((token, ok, rel))
    return out


def _arrived(root: pathlib.Path, path: str) -> bool:
    """Has the part a rule is waiting on been built? The first directory of the path decides."""
    if path.rstrip("/").endswith("CODEOWNERS"):
        return any((root / where / "CODEOWNERS").exists() for where in (".", "docs", ".github"))
    if path.startswith(".github/"):
        return (root / path).exists()
    return (root / path.split("/")[0]).exists()


def _held(cell: str, where: str, root: pathlib.Path, here: pathlib.Path) -> list:
    """A rule's check is a check that exists, or a part it is waiting on that does not exist yet."""
    problems = []
    waits = WAITING.findall(cell)
    for path in waits:
        if path.split("/")[0] not in PLANNED:
            problems.append("%s: waits on %s, which is not a planned part of this repo" % (where, path))
        elif _arrived(root, path):
            problems.append("%s: %s exists now; name the check that holds this rule" % (where, path))
    named = _named(WAITING.sub("", cell), root, here)
    checks = [token for token, ok, rel in named if ok and rel.parts[:1] and rel.parts[0] in CHECKS]
    if not waits and not checks:
        problems.append("%s: names no check; a check is a file or a test under %s" % (where, ", ".join(CHECKS)))
    # A test marked @pending is expected to fail: it holds nothing yet, and the rule must say so.
    unheld = [token for token in checks if _is_pending(token, root, here)]
    if unheld and PENDING not in cell:
        problems.append("%s: %s is expected to fail; say '%s'" % (where, unheld[0], PENDING))
    if PENDING in cell and not unheld:
        problems.append("%s: says '%s' and names no test marked @pending" % (where, PENDING))
    return problems


def _is_pending(token: str, root: pathlib.Path, here: pathlib.Path) -> bool:
    name, _, test = token.partition("::")
    target = root / name if (root / name).exists() else here / name
    if not test or not target.is_file():
        return False
    return re.search(r"@pending\s+def %s\(" % re.escape(test.split(".")[-1]), _text(target)) is not None


def _plain(text: str) -> list:
    """The lines of `text` that are not inside a code fence."""
    out, fenced = [], False
    for line in text.splitlines():
        if line.startswith("```"):
            fenced = not fenced
            continue
        out.append("" if fenced else line)
    return out


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


def _cells(line: str) -> list:
    """The cells of one table row. A pipe inside backticks, or after a backslash, is not a divider."""
    cells, cell, ticked, i = [], "", False, 0
    row = line.strip()
    row = row[1:] if row.startswith("|") else row
    while i < len(row):
        if row[i] == "\\" and row[i + 1:i + 2] == "|":
            cell, i = cell + "|", i + 2
            continue
        ticked = ticked != (row[i] == "`")
        if row[i] == "|" and not ticked:
            cells.append(cell.strip())
            cell = ""
        else:
            cell += row[i]
        i += 1
    return cells + ([cell.strip()] if cell.strip() else [])


def _tables(text: str) -> list:
    """Every table outside a code fence, as rows of cells, header first."""
    tables, table = [], []
    for line in _plain(text) + [""]:
        if line.lstrip().startswith("|"):
            table.append(_cells(line))
        elif table:
            tables.append(table)
            table = []
    return tables


def _rows(body: str) -> list:
    """The rows of the first table in `body`, without its header."""
    tables = _tables(body)
    return tables[0][2:] if tables else []


def _references(path: pathlib.Path, text: str, root: pathlib.Path) -> list:
    rel = path.relative_to(root)
    top = {p.name for p in root.iterdir()}
    problems = []
    for token, ok, _ in _named(WAITING.sub("", text), root, path.parent):
        if not ok:
            problems.append("%s: names %s, which is not in this repo" % (rel, token))
    for module in MODULE.findall(text):
        if module.split(".")[0] in top and not (root / (module.replace(".", "/") + ".py")).exists():
            problems.append("%s: runs %s, which is not in this repo" % (rel, module))
    if BARE_NUMBER.search(text):
        problems.append("%s: a bare issue or pull-request number; give its title" % rel)
    for block in re.split(r"\n\s*\n", text):
        for part in (block.splitlines() if block.lstrip().startswith("|") else [block]):
            if NUMBERED.search(part) and not TITLE.search(part):
                problems.append("%s: an issue or pull request is numbered without its title" % rel)
    return problems


def _agents_files(root: pathlib.Path) -> list:
    problems = []
    if not (root / "AGENTS.md").exists():
        return ["AGENTS.md is missing"]
    for path in _kept(root, "AGENTS.md"):
        rel, text = path.relative_to(root), _text(path)
        limit = ROOT_LINES if path.parent == root else LOCAL_LINES
        lines = text.splitlines()
        if len(lines) > limit:
            problems.append("%s is %d lines; the limit is %d. Move detail to a directory or to docs/"
                            % (rel, len(lines), limit))
        if any(len(line) > WIDTH for line in lines):
            problems.append("%s has a line over %d characters; the limit on lines is a limit on words" % (rel, WIDTH))
        if DATE.search(text):
            problems.append("%s holds a date; what is read on every task does not change with the day" % rel)
        held = 0
        for table in _tables(text):
            header = [c.lower() for c in table[0]]
            if header[-1:] != ["held by"]:
                if "rule" in header or "check" in header or "enforced by" in header:
                    problems.append("%s: a table of rules must end in a column headed 'Held by'" % rel)
                continue
            held += 1
            for cells in table[2:]:
                problems += _held(cells[-1], "%s, rule '%s'" % (rel, cells[0][:50]), root, path.parent)
        if not held:
            problems.append("%s: no table of rules and the checks that hold them" % rel)
    entry = root / "CLAUDE.md"
    if not entry.exists() or _text(entry).strip() != "@AGENTS.md":
        problems.append("CLAUDE.md must hold the one line @AGENTS.md, so that there is one set of rules")
    for name in sorted(OTHER_RULES):
        for path in _kept(root, name):
            if path != entry:
                problems.append("%s is a second set of rules; there is one, in AGENTS.md" % path.relative_to(root))
    for folder in (p for p in walk.folders(root) if not p.name.startswith(".")):
        if not (folder / "AGENTS.md").exists():
            problems.append("%s/ has no AGENTS.md" % folder.name)
    return problems


def _skills(root: pathlib.Path) -> list:
    """Each skill opens with the name and description its loader reads, and the root AGENTS.md points to it."""
    problems = []
    pointers = _text(root / "AGENTS.md") if (root / "AGENTS.md").exists() else ""
    for path in _skill_files(root):
        rel = path.relative_to(root).as_posix()
        if rel not in pointers:
            problems.append("%s: the root AGENTS.md does not point to it, and a skill loaded on demand alone is often "
                            "not loaded" % rel)
        front = FRONTMATTER.match(_text(path))
        if not front:
            problems.append("%s: opens with no frontmatter holding its name and description" % rel)
            continue
        fields = dict((k.strip(), v.strip()) for k, _, v in (ln.partition(":") for ln in front.group(1).splitlines()))
        if fields.get("name") != path.parent.name:
            problems.append("%s: is named %s; a skill is named for its directory" % (rel, fields.get("name") or "nothing"))
        if not fields.get("description"):
            problems.append("%s: no description; it is how a task finds the skill" % rel)
    return problems


def _decisions(root: pathlib.Path) -> list:
    problems = []
    records = sorted((root / "docs" / "decisions").glob("*.md"))
    if not records:
        return ["docs/decisions/ holds no record"]
    for want, path in enumerate(records, 1):
        text = _text(path)
        if not path.name.startswith("%04d-" % want):
            problems.append("docs/decisions/%s: records are numbered from 0001 with no gap" % path.name)
        if not text.startswith("# %04d. " % want):
            problems.append("docs/decisions/%s: the title must open with its number" % path.name)
        parts = dict(_sections(text, "## "))
        for need in ("Decision", "Why", "Boundaries"):
            if not parts.get(need, "").strip():
                problems.append("docs/decisions/%s: no section %s" % (path.name, need))
        for extra in sorted(set(parts) - {"Decision", "Why", "Boundaries"}):
            problems.append("docs/decisions/%s: a section '%s'; a record has Decision, Why and Boundaries"
                            % (path.name, extra))
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
    text = _text(path)
    problems, seen = [], set()
    for line in _plain(text):
        if re.match(r"#+\s+L-\d+", line) and not line.startswith("### "):
            problems.append("docs/lessons.md: '%s' must be a third-level heading to be read as a lesson" % line[:40])
    lessons = [(h, b) for h, b in _sections(text, "### ") if re.match(r"L-\d+\b", h)]
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
        text = _text(path)
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
            cited = [ln for ln in body.splitlines() if ln.startswith("Org standard:")]
            if not cited or not (cited[0].startswith("Org standard: none") or '"' in cited[0] or "/" in cited[0]):
                problems.append("%s: no 'Org standard:' line naming a file and a heading, or saying none" % where)
            if "```" not in body.split("Held by:")[0]:
                problems.append("%s: the example comes before the prose, and there is none" % where)
            problems += _held(held[0], where, root, folder)
    # The review standard is the rubric, as data, and a standard is one of the four pages.
    for path in sorted(folder.glob("*")) if folder.exists() else []:
        if "review" in path.name:
            problems.append("docs/standards/%s: the review standard is config/rubric-pr-review.json" % path.name)
        elif path.stem not in STANDARDS or path.suffix != ".md":
            problems.append("docs/standards/%s: the standards are %s; a new one is added to this check first"
                            % (path.name, ", ".join(STANDARDS)))
    return problems


def run(root: pathlib.Path = ROOT) -> list:
    problems = []
    for path in _markdown(root):
        problems += _references(path, _text(path), root)
    return problems + _agents_files(root) + _skills(root) + _decisions(root) + _lessons(root) + _standards(root)
