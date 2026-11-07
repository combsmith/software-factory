"""A decision record states what is decided now; to change one, add a record that replaces it.

Each record in `docs/decisions/` that the base holds is compared with this working tree, all of it
but two parts. Its Status may change once, in the change that replaces it, and only to "replaced
by" and the path, in backticks, of the record that replaces it: a record new in that change, whose
own Status says it replaces this one. After that the Status is fixed too. Its Boundaries may gain
rows, and a row's Check cell may change, since a row is added when the check for it is written and
that changes nothing decided; no row is taken away and no Boundary cell is changed. Everything
else, the title, the Decision and the Why among it, stays line for line as it was. A new record is
always allowed, but one whose Status says it replaces records replaces each of them, as above. In
every record a title comes first, then one `Status:` line; there is no HTML comment, which hides
text from a reader; and nothing in `docs/decisions/` is a link.

The base is the merge base of HEAD and refs/remotes/origin/main, named in full, read as the Stop
hook reads it (`tools/hooks/rules_changed.py`): git's replacement refs, grafts and commit graph off.
CI checks out the whole history for it. With a `.git` here, a directory or a worktree's file, and no
base to read, a shallow clone, no origin, no git, the check fails: it never passes what it could not
compare. With no `.git` at all the tree is an export, which has no history, and the comparison is
skipped; `verify` says so. In GitHub Actions a missing `.git` fails, so CI cannot skip it.
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
import pathlib
import re
import shutil
import subprocess

from tools.check_context import LINK, PENDING, TOKEN, WAITING, _cells, _is_pending, _rows, _sections

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASE = "refs/remotes/origin/main"
NO_GRAFTS = "/dev/null/grafts"      # a path that cannot exist: below a file, not a directory
SECONDS = 30                        # for each git command
FOLDER = "docs/decisions"
PATH = r"`(%s/(\d{4})-[^`/\s]+\.md)`" % FOLDER
# How decision 0012 says it was replaced, from the start of its Status: the path, then a comma, a stop or the end.
REPLACED = re.compile(r"^Status: replaced by %s(?=[,.]|$)" % PATH)
# How decision 0015 says what it replaces: one record, or a list of them, straight after its own Status.
REPLACES = re.compile(r"^Status: accepted\. Replaces (`[^`]+`(?:(?:, and |, | and )`[^`]+`)*)(?=[,.]|$)")
# Words that claim a replacement. Past the one declaration a Status makes, none of them, and no record's path, stands.
CLAIM = re.compile(r"replace|supersede", re.I)
NUMBER = re.compile(r"^(\d{4})-")
BOUNDARIES = "## Boundaries"
# A mutant a row names, by its description in tools/mutants.py (issue 590).
MUTANT = re.compile(r'mutant: "([^"\n]+)"')


class Unreadable(Exception):
    """The base could not be read, so nothing could be compared."""


def _git(root: pathlib.Path, *args: str) -> str:
    exe = shutil.which("git")
    if exe is None:
        raise Unreadable("git is not on PATH")
    # Only this tree's .git is read: no GIT_DIR or the like from whatever runs this. Replacement refs,
    # grafts and the commit graph are off, since any of them could make the base read as the change.
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env["GIT_GRAFT_FILE"] = NO_GRAFTS
    try:
        done = subprocess.run([exe, "--no-replace-objects", "-c", "core.commitGraph=false", *args], cwd=str(root),
                              env=env, capture_output=True, timeout=SECONDS)
    except (OSError, subprocess.TimeoutExpired):
        raise Unreadable("git %s did not finish" % args[0])
    if done.returncode != 0:
        raise Unreadable("git %s failed" % args[0])
    return done.stdout.decode("utf-8", "replace")


def base(root: pathlib.Path = ROOT):
    """The commit the records are compared with; None in an export, which has no `.git`. Raises Unreadable."""
    if not os.path.lexists(str(root / ".git")):
        if os.environ.get("GITHUB_ACTIONS"):
            raise Unreadable("there is no .git, and in GitHub Actions the checkout always writes one")
        return None
    if _git(root, "rev-parse", "--is-shallow-repository").strip() != "false":
        raise Unreadable("this clone is shallow")
    _git(root, "rev-parse", "--verify", "--quiet", BASE + "^{commit}")
    return _git(root, "merge-base", "HEAD", BASE).strip()


def described(root: pathlib.Path = ROOT) -> str:
    """What the records were compared with, for `verify` to print."""
    try:
        at = base(root)
    except Unreadable as err:
        return "unreadable (%s)" % err
    if at is None:
        return "skipped: no .git here, so this is an export with no history to compare with"
    return "compared with %s, the merge base with origin/main" % at[:12]


def _recorded(root: pathlib.Path, at: str) -> dict:
    """{path: text} of each record the base holds."""
    names = _git(root, "ls-tree", "-z", "--name-only", at, "--", FOLDER + "/").split("\0")
    return {name: _git(root, "cat-file", "blob", "%s:%s" % (at, name))
            for name in names if name.endswith(".md") and name.count("/") == FOLDER.count("/") + 1}


def _words(lines: list) -> str:
    return " ".join(" ".join(lines).split())


def parse(text: str):
    """(status, rest, rows) of a record, or a sentence saying why it cannot be read as one.

    `status` is the Status paragraph, its words joined by single spaces. `rows` is the Boundary
    cells, all but the Check, of each row of the first table under Boundaries. `rest` is every other
    line, as it stands but for space at its end, with the blank lines at the end of the file left out.
    """
    lines = [line.rstrip() for line in text.splitlines()]
    if "<!--" in text:
        return "it holds an HTML comment, which hides text from a reader"
    if not lines or not lines[0].startswith("# "):
        return "it must open with its title, on a line that opens '# '"
    starts = [i for i, line in enumerate(lines) if line.startswith("Status:")]
    first = next((i for i in range(1, len(lines)) if lines[i]), None)
    if len(starts) != 1 or starts[0] != first:
        return "it must have one line that opens 'Status:', the first after the title"
    end = next((i for i in range(first, len(lines)) if not lines[i]), len(lines))
    heads = [i for i, line in enumerate(lines) if line == BOUNDARIES]
    if len(heads) != 1 or heads[0] < end:
        return "it must have one line '%s', after its Status" % BOUNDARIES
    region = lines[heads[0]:]
    body = _body(region)
    rows = [tuple(" ".join(cell.split()) for cell in _cells(region[i])[:-1]) for i in body]
    rest = lines[:first] + lines[end:heads[0]] + [line for i, line in enumerate(region) if i not in body]
    while rest and not rest[-1]:
        rest.pop()
    return _words(lines[first:end]), rest, rows


def _body(region: list) -> range:
    """The rows of the first table in `region`, below its header and the line under it."""
    # A table may be indented, as Markdown and `check_context` read one (issue 590).
    top = next((i for i, line in enumerate(region) if line.lstrip().startswith("|")), len(region))
    bottom = next((i for i in range(top, len(region)) if not region[i].lstrip().startswith("|")), len(region))
    return range(top + 2, bottom)


def boundaries(text: str) -> list:
    """(Boundary cells, Check cell) of each row of the first table under Boundaries, as `check_context` reads the table,
    outside any fence and however it is indented; [] for a record `parse` cannot read (issue 590)."""
    if isinstance(parse(text), str):
        return []
    rows = _rows(dict(_sections(text, "## ")).get("Boundaries", ""))
    return [(tuple(" ".join(cell.split()) for cell in row[:-1]), " ".join(row[-1].split()) if row else "") for row in rows]


def _names(cell: str) -> list:
    """Every name a cell gives, as `check_context` reads them: in backticks, or as a link's target."""
    return TOKEN.findall(cell) + [m for m in LINK.findall(cell) if "://" not in m and not m.startswith("mailto:")]


def _tokens(cell: str) -> set:
    return set(_names(cell))


def _named_tests(cell: str) -> list:
    """(path, name) of each test a cell names as path::name, its path as the repo holds it, under `tests/`."""
    out = []
    for name in _names(cell):
        path, _, test = name.partition("::")
        path = _path(re.sub(r":\d+$", "", path))
        if test and path.split("/")[0] == "tests":
            out.append((path, test))
    return out


def _tests(cell: str) -> list:
    """(module, name) of each test a cell names as path::name."""
    return [(path[:-len(".py")].replace("/", "."), name) for path, name in _named_tests(cell)]


def _exempt(cell: str, root: pathlib.Path) -> bool:
    """Whether a row has no test that can kill a mutant yet: it waits on a planned part, or says it is not held yet,
    and every test it names is marked @pending (issue 590)."""
    return bool(WAITING.search(cell) or PENDING in cell) and \
        all(_is_pending("%s::%s" % (path, name), root, root) for path, name in _named_tests(cell))


def _is_tests(token: str) -> bool:
    return _path(token.partition("::")[0]).split("/")[0] == "tests"


def _same_check(old: str, new: str) -> bool:
    """Whether a row's Check is the one it was: the same names, but that a test file the old one named bare may now be
    named as a test of that file; the same mutants; and the same wait or the same word that it is not held yet, so a
    rule that stops waiting is a changed row (issue 590)."""
    was = _tokens(old)
    now = {t.partition("::")[0] if "::" in t and t.partition("::")[0] in was and _is_tests(t) else t for t in _tokens(new)}
    return (now == was and MUTANT.findall(old) == MUTANT.findall(new)
            and WAITING.findall(old) == WAITING.findall(new) and (PENDING in old) == (PENDING in new))


def _changed(old: list, new: list) -> list:
    """(number, row) of each row of `new` that is new or whose Check changed, against `old`, in order (issue 590)."""
    left, out = list(old), []
    for at, row in enumerate(new, 1):
        if row in left:
            left.remove(row)
            continue
        same = next((o for o in left if o[0] == row[0] and _same_check(o[1], row[1])), None)
        if same is not None:
            left.remove(same)
        else:
            out.append((at, row))
    return out


def _mutants(root: pathlib.Path) -> dict:
    """{description: (file, the tests that kill it)} of every mutant `tools/mutants.py` holds, read once for each root and
    each text of the file. Two
    that share a description name no one mutant. Raises Unreadable."""
    try:
        key = (str(root.resolve()), hashlib.sha256((root / "tools" / "mutants.py").read_bytes()).hexdigest())
    except OSError as err:
        raise Unreadable("tools/mutants.py cannot be read (%s)" % type(err).__name__)
    if key not in _READ:
        try:
            if root.resolve() == ROOT.resolve():
                from tools import mutants as module
            else:
                spec = importlib.util.spec_from_file_location("_mutants_of_%d" % len(_READ), str(root / "tools" / "mutants.py"))
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
            read = [(m[0], (m[1], tuple(m[4]))) for m in module.MUTANTS]
        except Exception as err:    # noqa: BLE001 -- whatever stops it being read, the mutants are unreadable
            raise Unreadable("tools/mutants.py cannot be read (%s)" % type(err).__name__)
        if len({name for name, _ in read}) != len(read):
            raise Unreadable("two mutants in tools/mutants.py share a description, so a row cannot name one of them")
        _READ[key] = dict(read)
    return _READ[key]


_READ = {}


def _is_test(killer: str, module: str, name: str) -> bool:
    """Whether a mutant's killer is the test `name` of `module`: a test of one class, by its module, its class and its
    own name, which the row gives as `Class.name`, or as `name` alone. A module or a class is not a test, whatever it
    is called (issue 590)."""
    parts = killer.split(".")
    if not killer.startswith(module + ".") or len(parts) != module.count(".") + 3:
        return False
    return ".".join(parts[-2:]) == name if "." in name else parts[-1] == name


def _path(name: str) -> str:
    """A path as the repo holds it, so that `./tests/x.py` and `tools/../tests/x.py` are `tests/x.py`. One that climbs
    out of the repo keeps its `..`, and so names nothing here."""
    parts = []
    for part in name.split("/"):
        if part in ("", "."):
            continue
        if part == ".." and parts and parts[-1] != "..":
            parts.pop()
        else:
            parts.append(part)
    return "/".join(parts)


def _named_mutant(rel: str, at: int, row: tuple, root: pathlib.Path, mutants: dict) -> list:
    """Why the row at boundary `at` does not name the mutant its test kills, or [] (issue 590)."""
    where, cell = "%s, boundary %d" % (rel, at), row[1]
    if _exempt(cell, root):
        return []
    named = MUTANT.findall(cell)
    if not named:
        return ['%s: a new or changed row names no mutant; name one as mutant: "<its description in tools/mutants.py>"'
                % where]
    tests = _tests(cell)
    if not tests:
        return ["%s: names no test for its mutant to be killed by; name it as path::name" % where]
    names = {_path(t.partition("::")[0]) for t in _tokens(" ".join(row[0]) + " " + cell)}
    problems = []
    for name in named:
        if name not in mutants:
            problems.append('%s: names mutant "%s", which tools/mutants.py does not hold' % (where, name))
            continue
        changed, killers = mutants[name]
        changed = _path(changed)
        if changed.split("/")[0] == "tests" or changed not in names:
            problems.append('%s: mutant "%s" changes %s, which this row does not name' % (where, name, changed))
        # The mutant is run against the tests it lists alone (tools/mutants.py), so each is one this row names.
        if not killers or not all(any(_is_test(k, module, test) for module, test in tests) for k in killers):
            problems.append('%s: mutant "%s" lists a test this row does not name, or none' % (where, name))
    return problems


def unnamed(root: pathlib.Path = ROOT) -> str:
    """How many Boundary rows name no mutant, of how many that could, for `verify` to print (issue 590)."""
    rows = [cell for path in sorted((root / FOLDER).glob("*.md"))
            for _, cell in boundaries(path.read_text(encoding="utf-8", errors="replace")) if not _exempt(cell, root)]
    return "%d of %d boundary rows name no mutant" % (sum(1 for c in rows if not MUTANT.search(c)), len(rows))


def held_by_rows(root: pathlib.Path = ROOT) -> set:
    """The description of each mutant a Boundary row names, which `tools/mutants.py` runs against its own tests alone."""
    return {name for path in sorted((root / FOLDER).glob("*.md"))
            for _, cell in boundaries(path.read_text(encoding="utf-8", errors="replace")) for name in MUTANT.findall(cell)}


def _declared(pattern, status: str):
    """`pattern` matched at the start of `status`, or None when it is not, or when what follows it claims more."""
    found = pattern.match(status)
    rest = status[found.end():] if found else ""
    if found is None or CLAIM.search(rest) or FOLDER + "/" in rest:
        return None
    return found


def _status(rel: str, old: str, new: str, before: dict, root: pathlib.Path) -> str:
    """Why the Status at `rel` may not change from `old` to `new`, or "" when it may."""
    if new == old:
        return ""
    if REPLACED.match(old):
        return "its Status named the record that replaces it, and is fixed from then on"
    named = _declared(REPLACED, new)
    if named is None:
        return ("its Status changes only to say what replaces it: 'Status: replaced by' and the path in backticks, "
                "as decision 0012's does, and nothing more of replacing or of another record")
    path, number = named.group(1), named.group(2)
    own = NUMBER.match(rel.rsplit("/", 1)[-1])
    if path in before:
        return "it names %s, which is not new in this change; the record that replaces it is" % path
    target = root / path
    if target.is_symlink() or not target.is_file():
        return "it names %s, which does not exist" % path
    if own is None or number <= own.group(1):
        return "it names %s, which is not a later record" % path
    said = parse(target.read_text(encoding="utf-8", errors="replace"))
    if rel not in (_replaces(said[0]) if isinstance(said, tuple) else []):
        return "%s's Status does not say it replaces this one: 'Status: accepted. Replaces' and its path" % path
    return ""


def _replaces(status: str) -> list:
    """The paths a Status names, in decision 0015's words, as the records it replaces."""
    listed = _declared(REPLACES, status)
    return re.findall(r"`([^`]+)`", listed.group(1)) if listed else []


def _replacing(rel: str, status: str, before: dict, current: dict) -> list:
    """Why the new record at `rel` does not replace what its Status says it does: each record it names is in the
    base, earlier, and in this change has its Status set to 'replaced by' this one."""
    if not CLAIM.search(status):
        return []
    names = _replaces(status)
    if not names:
        return ["its Status says what it replaces only as 'Status: accepted. Replaces' and each path in backticks, "
                "and nothing more of replacing or of another record"]
    own, why = NUMBER.match(rel.rsplit("/", 1)[-1]), []
    for name in names:
        number = NUMBER.match(name.rsplit("/", 1)[-1]) if re.fullmatch(PATH, "`%s`" % name) else None
        now = current.get(name)
        said = _declared(REPLACED, now[0]) if isinstance(now, tuple) else None
        if name not in before or number is None or now is None:
            why.append("it replaces %s, which is not a record main holds" % name)
        elif own is None or number.group(1) >= own.group(1):
            why.append("it replaces %s, which is not an earlier record" % name)
        elif said is None or said.group(1) != rel:
            why.append("it replaces %s, whose Status does not say 'replaced by' and this record's path" % name)
    return why


def _boundaries(old: list, new: list) -> str:
    """Why the Boundaries rows may not change from `old` to `new`, or "" when they may."""
    left = list(new)
    for row in old:
        if row not in left:
            return ("the row '%s' is gone or its Boundary changed; a row is only added, or its Check changed"
                    % " | ".join(row))
        left.remove(row)
    return ""


def _linked(root: pathlib.Path) -> list:
    folder = root / FOLDER
    if folder.is_symlink():
        return ["%s: is a link; the records are files here, which this check reads" % FOLDER]
    entries = sorted(folder.iterdir()) if folder.is_dir() else []
    return ["%s: is a link; a record is a file, which this check reads where it stands" % p.relative_to(root).as_posix()
            for p in entries if p.is_symlink()]


def _mutants_named(root: pathlib.Path, before: dict, texts: dict) -> list:
    """Why each Boundary row new in this change, or whose Check changed, or that names a mutant, does not name the
    mutant its test kills. Rows main holds that name none are left as they are (issue 590)."""
    problems, mutants = [], None
    for rel, text in sorted(texts.items()):
        rows = boundaries(text)
        fresh = dict(_changed(boundaries(before[rel]), rows) if rel in before else enumerate(rows, 1))
        for at, row in enumerate(rows, 1):
            if at not in fresh and not MUTANT.search(row[1]):
                continue
            if mutants is None and not _exempt(row[1], root):
                try:
                    mutants = _mutants(root)
                except Unreadable as err:
                    return problems + ["%s, boundary %d: %s, so no mutant it names can be read" % (rel, at, err)]
            problems += _named_mutant(rel, at, row, root, mutants or {})
    return problems


def run(root: pathlib.Path = ROOT) -> list:
    problems = _linked(root)
    folder = root / FOLDER
    current, texts = {}, {}
    for path in sorted(folder.glob("*.md")) if folder.is_dir() and not folder.is_symlink() else []:
        rel = path.relative_to(root).as_posix()
        if path.is_symlink() or not path.is_file():
            continue
        try:
            texts[rel] = path.read_text(encoding="utf-8")
            current[rel] = parse(texts[rel])
        except UnicodeDecodeError:
            current[rel] = "it is not UTF-8"
        if isinstance(current[rel], str):
            problems.append("%s: %s" % (rel, current[rel]))
    try:
        at = base(root)
        before = _recorded(root, at) if at else {}
    except Unreadable as err:
        return problems + ["the decision records cannot be compared with the merge base of HEAD and %s (%s); fetch "
                           "main's whole history (git fetch --unshallow origin, or git fetch origin main) and run "
                           "again" % (BASE, err)]
    for rel, new in sorted(current.items()):
        if at and rel not in before and isinstance(new, tuple):     # with no base, nothing is known to be new
            problems += ["%s: %s" % (rel, why) for why in _replacing(rel, new[0], before, current)]
    if at:
        problems += _mutants_named(root, before, texts)
    for rel, text in sorted(before.items()):
        old, new = parse(text), current.get(rel)
        if new is None:
            problems.append("%s: is gone; a record is never removed or renamed, so restore it, and add a record "
                            "that replaces it" % rel)
            continue
        if isinstance(new, str):
            continue        # said above
        if isinstance(old, str):
            problems.append("%s: the base's copy cannot be read as a record (%s), so it cannot be compared" % (rel, old))
            continue
        why = [w for w in (_status(rel, old[0], new[0], before, root),
                           "its title, Decision or Why changed" if old[1] != new[1] else "",
                           _boundaries(old[2], new[2])) if w]
        if why:
            problems.append("%s: %s; a record is never edited, only replaced: restore it, add a record that replaces "
                            "it, and set this one's Status to 'replaced by' and that record's path" % (rel, "; ".join(why)))
    return problems
