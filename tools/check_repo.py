"""What must never be in this repo: third-party code, a dependency manifest, a secret, a second definition."""
from __future__ import annotations

import ast
import hashlib
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKIP = {".git", "__pycache__", "corpus"}
LOCAL = {"kernel", "tools", "sim", "tests"}
# The standard-library modules in use. A new one is added here on purpose, in the same change.
STDLIB = {"__future__", "ast", "contextlib", "copy", "datetime", "hashlib", "io", "json", "os", "pathlib", "random", "re", "shutil",
          "subprocess", "sys", "tempfile", "typing", "unittest"}
# Ways to load code that the list above cannot see.
LOADERS = {"__import__", "exec", "eval", "compile"}
MANIFESTS = {"pyproject.toml", "setup.py", "setup.cfg", "Pipfile", "Pipfile.lock", "poetry.lock", "uv.lock",
             "package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "environment.yml", "go.mod",
             "Cargo.toml", "Gemfile"}
VENDORED = {"vendor", "vendored", "third_party", "site-packages", "node_modules"}
# The org's secrets baseline opens .gitignore, word for word (combsmith/.github, the
# gitignore standard, "L1 — Secrets baseline"). When the org changes it, copy the new block in
# and put its hash here; never edit between the markers.
BASELINE = re.compile(r"\A# >>> BEGIN combsmith secrets baseline.*?^# <<< END combsmith secrets baseline <<<$",
                      re.M | re.S)
BASELINE_SHA256 = "1d4a83d95f8ee135aee79215b022dce1ac1cf8e049642ef9e82f1a80b691bc37"
# The code owners file is the org's own, word for word (combsmith/.github, .github/CODEOWNERS;
# codeowners-standard.md, "Rule"). When the org changes it, copy it again and put its hash here.
CODEOWNERS_SHA256 = "3b957b2faa986898c05d1db8978f23d0be92a33cf338882a3f8b9bafa31918cb"
PYTHON = (3, 9)    # the oldest Python this must run on; newer syntax is refused, as far as this interpreter can tell
# Named in documents only. No code or data reaches into the proof-of-concept repo.
FOREIGN = ".github-" + "private"
# A model is named in one place, once the engine port exists. Until then, nowhere but the documents.
MODEL_ID = re.compile(r"\b(claude-[a-z0-9.-]*\d|gpt-\d[\w.-]*|gemini-\d[\w.-]*)")
TEXT = {".py", ".json", ".md", ".yml", ".yaml", ".txt", ".toml", ".cfg", ""}
# The shape of a credential. A secret is referred to by its name, never by its value. This is a
# net with wide holes; the org's push protection is the real one.
SECRETS = [re.compile(p) for p in (
    r"gh[pousr]_[A-Za-z0-9]{30,}", r"github_pat_[A-Za-z0-9_]{30,}", r"glpat-[A-Za-z0-9_-]{20,}",
    r"sk-(ant|proj)-[A-Za-z0-9_-]{20,}", r"AIza[0-9A-Za-z_-]{30,}", r"(AKIA|ASIA)[0-9A-Z]{16}",
    r"xox[abprs]-[A-Za-z0-9-]{10,}", r"-----BEGIN [A-Z ]*PRIVATE KEY",
)]


def _files(root: pathlib.Path) -> list:
    return sorted(p for p in root.rglob("*") if p.is_file() and not SKIP & set(p.relative_to(root).parts))


def _twice(body: list) -> list:
    """Names defined more than once in one scope: the later one silently replaces the earlier."""
    seen, out = set(), []
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            accessor = any(isinstance(d, ast.Attribute) and d.attr in ("setter", "getter", "deleter")
                           for d in node.decorator_list)
            if node.name in seen and not accessor:
                out.append((node.lineno, node.name))
            seen.add(node.name)
            if isinstance(node, ast.ClassDef):
                out += _twice(node.body)
    return out


def _python(rel: pathlib.PurePath, text: str) -> list:
    problems = []
    try:
        tree = ast.parse(text, str(rel), feature_version=PYTHON)
    except (SyntaxError, ValueError) as err:
        return ["%s:%s is not Python %d.%d: %s" % (rel, getattr(err, "lineno", 0), PYTHON[0], PYTHON[1], err)]
    for line, name in _twice(tree.body):
        problems.append("%s:%d defines %s a second time" % (rel, line, name))
    seeded = rel.parts[0] in ("sim", "tests")
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        mods = []
        if isinstance(node, ast.Import):
            mods = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and not node.level:
            mods = [node.module or ""]
            if node.module == "random" and any(alias.name != "Random" for alias in node.names):
                problems.append("%s:%d takes a draw from random by name; draw only with random()" % (rel, line))
        for mod in mods:
            if mod.split(".")[0] not in STDLIB | LOCAL:
                problems.append("%s:%d imports %s, which is not in the allowed list" % (rel, line, mod))
        if isinstance(node, ast.Name) and node.id in LOADERS:
            problems.append("%s:%d uses %s, which can load code no check has seen" % (rel, line, node.id))
        # Only random() gives the same sequence from the same seed on every Python version.
        if seeded and isinstance(node, ast.Attribute) and node.attr != "random":
            owner = node.value
            owner = owner.attr if isinstance(owner, ast.Attribute) else getattr(owner, "id", "")
            if owner == "rng":
                problems.append("%s:%d calls %s, whose sequence differs between Python versions"
                                % (rel, line, node.attr))
    return problems


def run(root: pathlib.Path = ROOT) -> list:
    problems = []
    ignore = root / ".gitignore"
    block = BASELINE.search(ignore.read_text(errors="replace")) if ignore.exists() else None
    if block is None:
        problems.append(".gitignore does not open with the org's secrets baseline, between its markers")
    elif hashlib.sha256(block.group(0).encode()).hexdigest() != BASELINE_SHA256:
        problems.append(".gitignore: the org's secrets baseline has been edited; copy it again, word for word")
    owners = root / ".github" / "CODEOWNERS"
    if not owners.exists():
        problems.append(".github/CODEOWNERS is missing; copy the org's, word for word")
    elif hashlib.sha256(owners.read_bytes()).hexdigest() != CODEOWNERS_SHA256:
        problems.append(".github/CODEOWNERS is not the org's file, word for word; copy it again")
    for stray in ("CODEOWNERS", "docs/CODEOWNERS"):
        if (root / stray).exists():
            problems.append("%s: GitHub reads the first code owners file it finds; keep only .github/CODEOWNERS" % stray)
    for path in _files(root):
        rel = path.relative_to(root)
        listed = path.name in MANIFESTS or (path.suffix in (".txt", ".in") and
                                            re.search(r"requirements|constraints", path.name))
        if listed:
            problems.append("%s: a dependency manifest; this repo installs nothing" % rel)
        if VENDORED & set(rel.parts):
            problems.append("%s: third-party code copied in is still third-party code" % rel)
        text = path.read_text(errors="replace")     # every file, whatever it is called
        for shape in SECRETS:
            if shape.search(text):
                problems.append("%s: holds something shaped like a credential" % rel)
        if path.suffix == ".py" and rel.parts[0] != "tests" and \
                re.search(r"(?:^test_)|(?:_tests?$)", path.stem):
            problems.append("%s: a test outside tests/ is never run" % rel)
        if rel.parts[0] == "tests" and path.suffix == ".py" and len(rel.parts) > 2:
            problems.append("%s: a test below tests/ is never found; keep tests in tests/ itself" % rel)
        if path.suffix not in TEXT:
            continue
        if path.suffix != ".md" and FOREIGN in text:
            problems.append("%s: names the proof-of-concept repo; nothing here depends on it" % rel)
        if rel.parts[0] != "docs" and MODEL_ID.search(text):
            problems.append("%s: names a model by its full id" % rel)
        if path.suffix == ".py":
            problems += _python(rel, text)
    return problems
