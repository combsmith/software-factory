"""What must never be in this repo: third-party code, a dependency manifest, a secret, a second definition, a link."""
from __future__ import annotations

import ast
import hashlib
import os
import pathlib
import re

from tools import walk

ROOT = pathlib.Path(__file__).resolve().parent.parent
LOCAL = {"kernel", "tools", "sim", "tests", "adapters", "controller"}
# The standard-library modules in use. A new one is added here on purpose, in the same change.
STDLIB = {"__future__", "ast", "contextlib", "copy", "datetime", "hashlib", "io", "json", "os", "pathlib", "random", "re", "shlex",
          "shutil", "subprocess", "sys", "tempfile", "time", "typing", "unittest"}
# Ways to load code that the list above cannot see.
LOADERS = {"__import__", "exec", "eval", "compile"}
# base64: tools/check_trials.py looks inside base64 for a credential.
STDLIB = STDLIB | {"base64"}
# urllib: tools/hooks/protected.py reads a URL's host with urllib.parse, not as a substring.
STDLIB = STDLIB | {"urllib"}
# concurrent and signal: tools/mutants.py runs one mutant to a CPU, and ends a run that hangs.
STDLIB = STDLIB | {"concurrent", "signal"}
# marshal: tests/test_transitions.py copies plain facts many thousand times, faster than copy or json can.
STDLIB = STDLIB | {"marshal"}
# difflib: tools/context_eval.py counts the lines a fresh agent's run added and removed, by file.
STDLIB = STDLIB | {"difflib"}
# importlib: tests/test_tools.py reads the import system's own suffixes, so that a Lens's inputs keep up with Python's.
STDLIB = STDLIB | {"importlib"}
# http: adapters/github.py, the one transport, refuses an answer http.client cut short. NETWORK refuses it anywhere else.
STDLIB = STDLIB | {"http"}
# zipfile and zlib: adapters/artifacts.py opens a Run's artifact, a zip GitHub serves, of one file and bounded.
STDLIB = STDLIB | {"zipfile", "zlib"}
# The network. Only the one transport reaches it, so a request to GitHub is made in one file a review can read whole;
# everywhere else these are refused, the required check fetches nothing, and a test replays what a trial recorded.
# A net, as the search for secrets is: a subprocess or importlib can still reach out, and review is the real guard.
NETWORK = {"urllib.request", "http", "socket", "ssl", "ftplib", "smtplib", "imaplib", "poplib", "nntplib",
           "telnetlib", "xmlrpc", "socketserver", "asyncio", "webbrowser"}
TRANSPORT = pathlib.PurePosixPath("adapters/github.py")
# The one exception, decision 0044's Boundaries (the Maintainer's ruling on issue 287): P-50's stub of the model's API,
# which serves the pinned CLI canned answers on the canary's runner, and its tests' stand-in on 127.0.0.1 here. It is
# held by an allowlist, not a list of what is refused: it imports these modules alone, by their own names; of http, os
# and sys it names these alone; it makes its server one way, http.server.HTTPServer(("127.0.0.1", <port>), <handler>),
# written as it is; it calls no builtin that reaches round a name, and touches no socket, bind or server_bind; and no
# workflow of this repo names it.
TRIAL_STUB = pathlib.PurePosixPath("tools/trial_p50_stub.py")
STUB_IMPORTS = {"http.server", "json", "os", "sys"}
STUB_NAMES = {"http.server.HTTPServer", "http.server.BaseHTTPRequestHandler", "os.replace", "sys.argv", "sys.exit"}
STUB_SERVER = "http.server.HTTPServer"
STUB_BUILTINS = {"getattr", "setattr", "delattr", "vars", "globals", "locals", "__import__", "eval", "exec", "compile"}
STUB_ATTRS = {"socket", "bind", "server_bind", "connect", "create_connection", "create_server", "socketserver"}
LOOPBACK = "127.0.0.1"


def _dotted(node):
    """The name an attribute chain spells, as a.b.c, when it starts at a plain name; else None."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    return ".".join([node.id] + parts[::-1]) if isinstance(node, ast.Name) else None


def _stub(rel: pathlib.PurePath, tree) -> list:
    """What P-50's stub does beyond the allowlist above."""
    problems = []
    inner = {id(node.value) for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    calls = {id(node.func): node for node in ast.walk(tree) if isinstance(node, ast.Call)}
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.ImportFrom):
            problems.append("%s:%d imports from %s; the stub imports whole modules by their own names" % (rel, line, node.module))
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name not in STUB_IMPORTS or alias.asname:
                    problems.append("%s:%d imports %s, which the stub may not" % (rel, line, alias.name))
        if isinstance(node, ast.Name) and node.id in STUB_BUILTINS:
            problems.append("%s:%d uses %s, which reaches round a name" % (rel, line, node.id))
        if isinstance(node, ast.Name) and node.id in ("http", "os", "sys") and id(node) not in inner:
            problems.append("%s:%d names %s itself, not one of the names it may use" % (rel, line, node.id))
        if isinstance(node, ast.Attribute):
            if node.attr in STUB_ATTRS or node.attr == "server_address" and isinstance(node.ctx, ast.Store):
                problems.append("%s:%d touches %s; the stub serves and never reaches out" % (rel, line, node.attr))
            spelt = _dotted(node)
            if id(node) in inner or spelt is None or spelt.split(".")[0] not in ("http", "os", "sys"):
                continue
            if spelt not in STUB_NAMES:
                problems.append("%s:%d names %s, which the stub may not" % (rel, line, spelt))
            elif spelt == STUB_SERVER:
                call = calls.get(id(node))
                host = call.args[0].elts[0] if call and len(call.args) == 2 and not call.keywords \
                    and isinstance(call.args[0], ast.Tuple) and len(call.args[0].elts) == 2 else None
                if not (isinstance(host, ast.Constant) and host.value == LOOPBACK):
                    problems.append("%s:%d makes its server other than as HTTPServer((\"%s\", port), handler)"
                                    % (rel, line, LOOPBACK))
    return problems
# The one host off GitHub's API the transport reaches, an artifact's storage (the Maintainer's ruling on #192): no other
# code names it, so no other code builds an address there; a test may, to answer for it.
STORAGE = re.compile(r"blob\.core\.windows\.net|githubusercontent\.com", re.IGNORECASE)
MANIFESTS = {"pyproject.toml", "setup.py", "setup.cfg", "Pipfile", "Pipfile.lock", "poetry.lock", "uv.lock",
             "package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "environment.yml", "go.mod",
             "Cargo.toml", "Gemfile"}
VENDORED = {"vendor", "vendored", "third_party", "site-packages", "node_modules"}
# The links this repo needs, by path from the root. There are none. Every path is held to a rule by
# some check, if only this one's search for secrets, and a check reads a path where it stands: behind a
# link to a directory it reads nothing, since tools/walk.py never follows one, and through a link to a
# file it reads what another path holds, under that path's review. A link that is truly needed is
# named here, with its reason, in the same change.
LINKS = set()
# Compiled code. Python loads it ahead of the source beside it, or with none there, and no check reads it.
COMPILED = {".pyc", ".pyo", ".so", ".pyd"}
# The org's secrets baseline opens .gitignore, word for word (combsmith/.github, the
# gitignore standard, "L1 — Secrets baseline"). When the org changes it, copy the new block in
# and put its hash here; never edit between the markers.
BASELINE = re.compile(r"\A# >>> BEGIN combsmith secrets baseline.*?^# <<< END combsmith secrets baseline <<<$",
                      re.M | re.S)
BASELINE_SHA256 = "5923c09c4183e1c104f3c04f57eba4d86ae5547913321c6d8bc053bf81d95a57"
# The code owners file is the org's own, word for word (combsmith/.github, .github/CODEOWNERS;
# codeowners-standard.md, "Rule"). When the org changes it, copy it again and put its hash here.
CODEOWNERS_SHA256 = "64da42e5c2edba9d9c92680f5b106be149ed4c5336b2b2e5c0beeec9340864e2"
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
    transport = pathlib.PurePosixPath(*rel.parts) == TRANSPORT
    stub = pathlib.PurePosixPath(*rel.parts) == TRIAL_STUB
    if stub:
        problems += _stub(rel, tree)
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and STORAGE.search(node.value) \
                and not transport and rel.parts[0] != "tests":
            problems.append("%s:%d names GitHub's artifact storage, which only %s reaches" % (rel, line, TRANSPORT))
        mods = []
        if isinstance(node, ast.Import):
            mods = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and not node.level:
            mods = [node.module or ""]
            reached = ["%s.%s" % (node.module, alias.name) for alias in node.names] if node.module else []
            if node.module == "random" and any(alias.name != "Random" for alias in node.names):
                problems.append("%s:%d takes a draw from random by name; draw only with random()" % (rel, line))
        for mod in mods:
            if mod.split(".")[0] not in STDLIB | LOCAL:
                problems.append("%s:%d imports %s, which is not in the allowed list" % (rel, line, mod))
        for mod in mods + (reached if isinstance(node, ast.ImportFrom) and not node.level else []):
            served = stub and mod == "http.server" and isinstance(node, ast.Import)
            if any(mod == net or mod.startswith(net + ".") for net in NETWORK) and not transport and not served:
                problems.append("%s:%d imports %s, which reaches the network; only %s does, as the one transport"
                                % (rel, line, mod, TRANSPORT))
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


def _unloadable(rel: pathlib.PurePath) -> list:
    """What is wrong with a path by its name alone: code Python loads that no check reads, or local output.

    Names in any case: a file system that folds case opens .PYC, __PYCACHE__/ or .GITMODULES as Python or git asks.
    """
    problems, folded = [], [part.casefold() for part in rel.parts]
    if folded[-1] == ".gitmodules":
        problems.append("%s: declares a submodule, whose files come from another repo, at a commit this repo's "
                        "review never sees; commit the files themselves" % rel)
    if rel.suffix.casefold() in COMPILED:
        problems.append("%s: compiled code; Python loads it ahead of, or instead of, the reviewed source, and no "
                        "check reads it; commit the source only" % rel)
    # tools/walk.py lists what is in these folders only when git's index holds it.
    if walk.SKIP & set(folded[:-1]):
        problems.append("%s: in __pycache__/, Python's local output, committed; Python loads it ahead of the "
                        "reviewed source, and no check reads it; remove it from git" % rel)
    if len(rel.parts) > 1 and folded[0] in walk.ROOT_ONLY:
        problems.append("%s: in corpus/, local output make_corpus.py writes, committed; nothing reads it from "
                        "git, and the corpus is remade from the Kernel; remove it from git" % rel)
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
    try:
        held = walk.index(root) or {}
    except ValueError as err:
        held = {}
        problems.append("git's index cannot be read (%s), so what is committed cannot be told from local output, "
                        "and none is skipped" % err)
    for rel, mode in sorted(held.items()):
        if mode == walk.GITLINK:
            problems.append("%s: a submodule; its files come from another repo, at a commit this repo's review never "
                            "sees, and no check reads them; commit the files themselves" % rel)
        elif not os.path.lexists(str(root / rel)):
            # Staged, then deleted with the deletion not staged: the walk below cannot see it, and the next commit takes it.
            problems += _unloadable(pathlib.PurePosixPath(rel))
    for path in walk.links(root):
        rel = path.relative_to(root)
        if not path.exists():
            problems.append("%s: a link to nothing; commit what it points at, or remove it" % rel)
        elif rel.as_posix() in LINKS:
            continue
        elif path.is_dir():
            problems.append("%s: a link to a directory; Python imports through it, but no check reads behind it, "
                            "because tools/walk.py never follows a link; commit the files themselves" % rel)
        else:
            problems.append("%s: a link to a file; what it holds is changed at another path, under that path's "
                            "rules and review, and may lie outside the repo; commit the file itself" % rel)
    for path in walk.files(root):
        rel = path.relative_to(root)
        listed = path.name in MANIFESTS or (path.suffix in (".txt", ".in") and
                                            re.search(r"requirements|constraints", path.name))
        if listed:
            problems.append("%s: a dependency manifest; this repo installs nothing" % rel)
        if VENDORED & set(rel.parts):
            problems.append("%s: third-party code copied in is still third-party code" % rel)
        problems += _unloadable(rel)
        text = path.read_text(errors="replace")     # every file, whatever it is called
        for shape in SECRETS:
            if shape.search(text):
                problems.append("%s: holds something shaped like a credential" % rel)
        if rel.parts[:2] == (".github", "workflows") and TRIAL_STUB.stem in text:
            problems.append("%s names %s, which runs only in the canary's workflow" % (rel, TRIAL_STUB))
        if path.suffix == ".py" and rel.parts[0] != "tests" and \
                re.search(r"(?:^test_)|(?:_tests?$)", path.stem):
            problems.append("%s: a test outside tests/ is never run" % rel)
        if rel.parts[0] == "tests" and path.suffix == ".py" and len(rel.parts) > 2:
            problems.append("%s: a test below tests/ is never found; keep tests in tests/ itself" % rel)
        if path.suffix not in TEXT:
            continue
        # A fixture keeps what GitHub said, which may name either. check_trials.py keeps all else out of trials/.
        recorded = len(rel.parts) == 2 and rel.parts[0] == "trials" and path.suffix == ".json"
        if path.suffix != ".md" and FOREIGN in text and not recorded:
            problems.append("%s: names the proof-of-concept repo; nothing here depends on it" % rel)
        if rel.parts[0] != "docs" and MODEL_ID.search(text) and not recorded:
            problems.append("%s: names a model by its full id" % rel)
        if path.suffix == ".py":
            problems += _python(rel, text)
    return problems
