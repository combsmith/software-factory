"""The context's test (issue 8): what one run of a fresh agent is recorded as, with no text of the model's in it.

`tools/context_eval.sh` runs the agent on an export of one commit, judges what it left, and calls this module to write
the run's record, a `context-eval/1` run, from the CLI's transcript, the export before and after, the verdicts and the
run's facts. Nothing here runs a model, and nothing here reads the held-out answer: the runner copies it in, runs it,
and takes it out before this module is called.

    python3 -m tools.context_eval record TRANSCRIPT PRISTINE WORK VERDICTS META OUT
    python3 -m tools.context_eval mutants PRISTINE WORK

`record` writes OUT, the run's record, and exits 0; 2 when a file cannot be read, and then writes nothing. Every path
is followed to where it really is and must lie under the system's scratch directory, where the runner keeps its own:
the transcript is the model's own words and is never inside the repo, nor is the record written there. TRANSCRIPT is
the CLI's output, as `--output-format stream-json` or `json` gives it; only the names of the tools it used, the paths
and the first words of the commands they were given, and the result's counts are taken from it, never a text block, a
tool's result, a prompt or an answer. PRISTINE and WORK are the export as made and as the agent left it; what differs
between them is counted, by file, in lines. VERDICTS is JSON with `held_out_test`, `verify` and `mutant`, which the
runner judged. META is JSON with `commit`, `ran_at`, `cli_version`, `cap_turns` and `code`, the reason code the task
sentence names. `mutants` prints, as JSON, the names and targets of the mutants WORK's `tools/mutants.py` holds that
PRISTINE's does not, for the runner to break.
"""
from __future__ import annotations

import difflib
import json
import os
import pathlib
import re
import sys
import tempfile

from tools import walk
from tools.check_trials import shaped
from tools.jsonschema_lite import validate

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCHEMA = json.loads((ROOT / "schemas" / "context-eval.schema.json").read_text())
RUN_SCHEMA = SCHEMA["properties"]["runs"]["items"]
# What is taken from a tool's input: a path, by these names, and a command's first words, by this one.
PATH_INPUTS = ("file_path", "path", "notebook_path")
COMMAND_INPUT = "command"
PATH = re.compile(r"^\.?[A-Za-z0-9_][A-Za-z0-9_./-]{0,199}$")
WORD = re.compile(r"^[a-z0-9_./=-]+$")
FIRST_WORDS = 4
UNREADABLE = "unreadable"
TOKEN_LENGTH = 24      # a word longer than this, of letters and digits, is read as a token and never recorded
# A mutant's entry in tools/mutants.py: its name, then the file it targets.
MUTANT = re.compile(r'^\s*\(\s*"([^"\n]+)",\s*(?:"([^"\n]+)"|([A-Z_]+))\s*,', re.M)
# A mutant's name as the house style writes one: words, a few marks, no quotes; the schema holds it to the same.
MUTANT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _:'(),.-]{0,119}$")


def _messages(text: str) -> list:
    """The transcript's messages, as dictionaries: one JSON value that is a list or an object, or one object a line."""
    try:
        said = json.loads(text)
    except ValueError:
        said = None
    if isinstance(said, list):
        return [m for m in said if isinstance(m, dict)]
    if isinstance(said, dict):
        return [said]
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if isinstance(item, dict):
            out.append(item)
    return out


def _relative(given: str, work: pathlib.Path):
    """A path the agent named, relative to the export when it is inside it, every `..` and link resolved; None when
    it is not a path, or outside the export."""
    if not isinstance(given, str) or not given.strip():
        return None
    try:
        base = os.path.realpath(str(work))
        resolved = os.path.realpath(given if os.path.isabs(given) else os.path.join(base, given))
    except (ValueError, OSError):
        return None
    if not resolved.startswith(base + os.sep):
        return None
    rel = os.path.relpath(resolved, base)
    return rel if PATH.match(rel) else None


def _first_words(command) -> str:
    """A command's first words, each held to WORD and to no credential's shape; a word that is not one ends the
    record of it, and a command with no such word is unreadable."""
    if not isinstance(command, str):
        return UNREADABLE
    words = []
    for word in command.strip().split()[:FIRST_WORDS]:
        if not WORD.match(word) or _token(word):
            break
        words.append(word)
    return " ".join(words) if words else UNREADABLE


def _token(word: str) -> bool:
    """Whether a word is shaped like a credential, by the trials' rules or by its length with letters and digits."""
    return shaped(word) or (len(word) > TOKEN_LENGTH and re.search(r"[0-9]", word) is not None
                            and re.search(r"[a-z]", word) is not None)


def reads_and_commands(text: str, work: pathlib.Path) -> tuple:
    """(the paths the agent read, in order, each once; the first words of each command it ran, in order; the result's
    counts; how many paths it named outside the export), from the transcript. Only a tool_use block's name and the
    named inputs are read; a text block, a tool's result and the result's text are never."""
    read, ran, counts, seen, outside = [], [], {}, set(), 0
    for message in _messages(text):
        if message.get("type") == "result":
            usage = message.get("usage") if isinstance(message.get("usage"), dict) else {}
            counts = {"turns": message.get("num_turns"), "duration_ms": message.get("duration_ms"),
                      "usd": message.get("total_cost_usd"), "input_tokens": usage.get("input_tokens"),
                      "output_tokens": usage.get("output_tokens")}
            continue
        inner = message.get("message") if isinstance(message.get("message"), dict) else message
        content = inner.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            given = block.get("input") if isinstance(block.get("input"), dict) else {}
            if COMMAND_INPUT in given:
                ran.append(_first_words(given[COMMAND_INPUT]))
            for key in PATH_INPUTS:
                if key in given:
                    path = _relative(given[key], work)
                    if path is None:
                        outside += 1
                    elif path not in seen:
                        seen.add(path)
                        read.append(path)
    return read, ran, counts, outside


LINK = "\0link"     # what a link is held as: it is never followed, so what it points at is never read


def _own(folder: pathlib.Path, path: pathlib.Path) -> bool:
    """Whether `path` is a file of the export's own: not a link, and inside `folder` when every link on the way to it
    is followed. A link the agent left may point anywhere, and what it points at is not the export's."""
    if path.is_symlink() or not path.is_file():
        return False
    return os.path.realpath(str(path)).startswith(os.path.realpath(str(folder)) + os.sep)


def _files(folder: pathlib.Path) -> dict:
    """Every file under `folder` by its relative path, with its text, as the one walk lists an export; a file that is
    not text is held by its bytes' size, and a link by LINK, never by what it points at."""
    out = {}
    for path in walk.files(folder):
        rel = path.relative_to(folder).as_posix()
        if path.is_symlink():
            out[rel] = LINK
            continue
        if not _own(folder, path):
            continue
        try:
            out[rel] = path.read_text()
        except (UnicodeDecodeError, OSError):
            out[rel] = "\0%d" % path.stat().st_size
    return out


def changes(pristine: pathlib.Path, work: pathlib.Path) -> list:
    """Each file that differs between the export as made and as the agent left it, with the lines added and removed."""
    before, after = _files(pristine), _files(work)
    out = []
    for rel in sorted(set(before) | set(after)):
        if before.get(rel) == after.get(rel) or not PATH.match(rel):
            continue
        old = before.get(rel, "").splitlines()
        new = after.get(rel, "").splitlines()
        added = removed = 0
        for line in difflib.unified_diff(old, new, lineterm="", n=0):
            if line.startswith("+") and not line.startswith("+++"):
                added += 1
            elif line.startswith("-") and not line.startswith("---"):
                removed += 1
        out.append({"path": rel, "added": added, "removed": removed})
    return out


def _mutant_entries(folder: pathlib.Path) -> list:
    """Each mutant tools/mutants.py under `folder` holds, as (name, target), a target named by a constant of that file
    read through it."""
    path = folder / "tools" / "mutants.py"
    text = path.read_text() if _own(folder, path) else ""
    named = dict(re.findall(r'^([A-Z_]+) = "([^"\n]+)"$', text, re.M))
    return [(m.group(1), m.group(2) or named.get(m.group(3), m.group(3))) for m in MUTANT.finditer(text)]


def new_mutants(pristine: pathlib.Path, work: pathlib.Path) -> list:
    """The mutants WORK's tools/mutants.py holds that PRISTINE's does not, as (name, target)."""
    before = set(_mutant_entries(pristine))
    return [entry for entry in _mutant_entries(work) if entry not in before]


def mutants_kept(pristine: pathlib.Path, work: pathlib.Path) -> bool:
    """Whether every mutant the export held as made is still in it: an agent that drops one has broken the check."""
    return set(_mutant_entries(pristine)) <= set(_mutant_entries(work))


def new_tests(pristine: pathlib.Path, work: pathlib.Path) -> list:
    """The tests WORK's tests/ hold that PRISTINE's do not, as tests/<file>.py::<name>."""
    def names(folder):
        out = set()
        for path in (walk.files(folder, "tests") if (folder / "tests").is_dir() else []):
            rel = path.relative_to(folder).as_posix()
            if not (path.name.startswith("test_") and path.suffix == ".py") or not _own(folder, path):
                continue
            for m in re.finditer(r"^\s*def (test_[a-z0-9_]+)\(", path.read_text(), re.M):
                out.add("%s::%s" % (rel, m.group(1)))
        return out
    return sorted(names(work) - names(pristine))


def record(transcript: str, pristine: pathlib.Path, work: pathlib.Path, verdicts: dict, meta: dict):
    """One run's record, valid against context-eval/1's run, or None when what it was given does not make one."""
    if not isinstance(verdicts, dict) or not isinstance(meta, dict):
        return None
    read, ran, counts, outside = reads_and_commands(transcript, work)
    changed = changes(pristine, work)
    mutants = new_mutants(pristine, work)
    tests = new_tests(pristine, work)
    code = meta.get("code")
    # The reason code counts as added only on a line the agent added to the Kernel, as a whole word.
    added_lines = []
    for change in changed:
        rel = change["path"]
        if rel.startswith("kernel/") and _own(work, work / rel):
            old = (pristine / rel).read_text().splitlines() if _own(pristine, pristine / rel) else []
            added_lines += [line for line in difflib.unified_diff(old, (work / rel).read_text().splitlines(), lineterm="", n=0)
                            if line.startswith("+") and not line.startswith("+++")]
    reason = (code if isinstance(code, str) and re.fullmatch(r"[a-z_]+", code)
              and any(re.search(r"(?<![a-z_])%s(?![a-z_])" % re.escape(code), line) for line in added_lines) else None)
    mutant = mutants[0][0] if mutants else None
    if mutant is not None and (any(_token(word) for word in mutant.split()) or not MUTANT_NAME.match(mutant)):
        mutant = None
    judged = {k: verdicts.get(k) for k in ("held_out_test", "verify", "mutant")}
    if judged["mutant"] == "killed" and not mutants_kept(pristine, work):
        judged["mutant"] = "survived"       # a mutant dropped from the list is one that cannot have been killed
    restored = meta.get("restored") if isinstance(meta.get("restored"), list) else []
    run = {
        "commit": meta.get("commit"), "ran_at": meta.get("ran_at"), "cli_version": meta.get("cli_version"),
        "cap_turns": meta.get("cap_turns"),
        "read": read, "outside_reads": outside, "ran": ran, "unread_commands": ran.count(UNREADABLE),
        "changed": changed, "restored": restored,
        "added": {"test": tests[0] if tests else None, "mutant": mutant, "reason": reason},
        "cost": {k: counts.get(k) for k in ("turns", "duration_ms", "usd", "input_tokens", "output_tokens")},
        "verdicts": judged,
    }
    run["passed"] = (run["verdicts"]["held_out_test"] == "pass" and run["verdicts"]["verify"] == "pass"
                     and run["verdicts"]["mutant"] == "killed")
    return run if not validate(run, RUN_SCHEMA) else None


def main(argv: list, base: pathlib.Path = None) -> int:
    mode = argv[0] if argv else ""
    if not ((mode == "mutants" and len(argv) == 3) or (mode == "record" and len(argv) == 7)):
        print("usage: python3 -m tools.context_eval record TRANSCRIPT PRISTINE WORK VERDICTS META OUT\n"
              "       python3 -m tools.context_eval mutants PRISTINE WORK", file=sys.stderr)
        return 2
    # Every path is followed to where it really is, and one outside the scratch directory, where the runner keeps the
    # export, the transcript and the record, is refused before it is opened; the refusal names no path.
    inside = os.path.realpath(str(tempfile.gettempdir() if base is None else base))
    real = [os.path.realpath(p) for p in argv[1:]]
    if not all(path.startswith(inside + os.sep) for path in real):
        print("context_eval: every path stays in the scratch directory, outside the repo", file=sys.stderr)
        return 2
    if mode == "mutants":
        pristine, work = pathlib.Path(real[0]), pathlib.Path(real[1])
        if not (pristine.is_dir() and work.is_dir()):
            print("context_eval: PRISTINE and WORK must be directories", file=sys.stderr)
            return 2
        found = new_mutants(pristine, work)
        print(json.dumps({"names": [n for n, _ in found], "targets": sorted({t for _, t in found})}))
        return 0
    transcript, pristine, work, verdicts, meta, out = real
    try:
        with open(transcript, encoding="utf-8") as first, open(verdicts, encoding="utf-8") as second, \
                open(meta, encoding="utf-8") as third:
            text, judged, facts = first.read(), json.load(second), json.load(third)
    except (OSError, ValueError):
        print("context_eval: a file cannot be read", file=sys.stderr)
        return 2
    run = record(text, pathlib.Path(pristine), pathlib.Path(work), judged, facts)
    if run is None:
        print("context_eval: what was given does not make a run's record", file=sys.stderr)
        return 2
    with open(out, "w", encoding="utf-8") as record_file:
        record_file.write(json.dumps(run, indent=2) + "\n")
    print("recorded: %s" % ("passed" if run["passed"] else "failed"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
