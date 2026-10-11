"""What must never be in this repo: third-party code, a dependency manifest, a secret, a second definition."""
from __future__ import annotations

import ast
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKIP = {".git", "__pycache__", "corpus"}
LOCAL = {"kernel", "tools", "sim", "tests"}
# The standard-library modules in use. A new one is added here on purpose, in the same change.
STDLIB = {"__future__", "ast", "copy", "datetime", "json", "os", "pathlib", "random", "re", "shutil",
          "subprocess", "sys", "tempfile", "typing", "unittest"}
MANIFESTS = {"requirements.txt", "pyproject.toml", "setup.py", "setup.cfg", "Pipfile", "poetry.lock",
             "package.json", "uv.lock"}
PYTHON = (3, 9)    # the oldest Python this must run on; newer syntax is refused
# Named in documents only. No code or data reaches into the proof-of-concept repo.
FOREIGN = ".github-" + "private"
# A model is named by family in one place, once the engine port exists. Until then, nowhere.
MODEL_ID = re.compile(r"\bclaude-[a-z]+-\d")
# Only random() gives the same sequence from the same seed on every Python version.
UNSTABLE = {"choice", "choices", "shuffle", "sample", "randint", "randrange"}
TEXT = {".py", ".json", ".md", ".yml", ".yaml", ".txt", ".toml", ".cfg", ""}
# The shape of a credential. A secret is referred to by its name, never by its value.
SECRETS = [re.compile(p) for p in (
    r"gh[pousr]_[A-Za-z0-9]{30,}", r"github_pat_[A-Za-z0-9_]{30,}", r"sk-ant-[A-Za-z0-9_-]{20,}",
    r"AKIA[0-9A-Z]{16}", r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
)]


def _files(root: pathlib.Path) -> list:
    return sorted(p for p in root.rglob("*") if p.is_file() and not SKIP & set(p.relative_to(root).parts))


def _twice(body: list) -> list:
    """Names defined more than once in one scope: the later one silently replaces the earlier."""
    seen, out = set(), []
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            if node.name in seen:
                out.append((node.lineno, node.name))
            seen.add(node.name)
            if isinstance(node, ast.ClassDef):
                out += _twice(node.body)
    return out


def run(root: pathlib.Path = ROOT) -> list:
    problems = []
    for path in _files(root):
        rel = path.relative_to(root)
        if path.name in MANIFESTS or path.name.startswith("requirements"):
            problems.append("%s: a dependency manifest; this repo installs nothing" % rel)
        if path.suffix not in TEXT:
            continue
        text = path.read_text(errors="replace")
        for shape in SECRETS:
            if shape.search(text):
                problems.append("%s: holds something shaped like a credential" % rel)
        if path.suffix != ".md" and FOREIGN in text:
            problems.append("%s: names the proof-of-concept repo; nothing here depends on it" % rel)
        if path.suffix != ".md" and MODEL_ID.search(text):
            problems.append("%s: names a model by its full id" % rel)
        if path.suffix != ".py":
            continue
        try:
            tree = ast.parse(text, str(path), feature_version=PYTHON)
        except SyntaxError as err:
            problems.append("%s:%s is not Python %d.%d: %s" % ((rel, err.lineno) + PYTHON + (err.msg,)))
            continue
        for line, name in _twice(tree.body):
            problems.append("%s:%d defines %s a second time" % (rel, line, name))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in UNSTABLE:
                problems.append("%s:%d calls %s, whose sequence differs between Python versions"
                                % (rel, node.lineno, node.attr))
            mods = []
            if isinstance(node, ast.Import):
                mods = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                mods = [node.module or ""]
            for mod in mods:
                if mod.split(".")[0] not in STDLIB | LOCAL:
                    problems.append("%s:%d imports %s, which is not in the allowed list" % (rel, node.lineno, mod))
    return problems
