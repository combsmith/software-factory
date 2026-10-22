"""The eval job, `factory / eval` (design §4.9 and §3.14, issue 309): the review Intent's held-out set, run on the commit
it judges and scored against its rubric, so that what is measured is what runs. Its steps are modules of their own,
each a `run:` line of `.github/workflows/eval.yml`, in this order:

- `plan` reads the set's manifest at the commit and the Release the dispatch names; a set of no case ends the run here,
  `eval_set_empty`, before any credential is minted (ruling 8);
- `fetch` reads each case from the private home through `adapters/heldout.py`, with the token the job minted for it, into
  a scratch directory outside the workspace, on a runner thrown away when the job ends;
- `run` gives each case to the review Intent and scores its Result with `tools/eval_result.py` (the ruling's PR 2);
- `judge` fails the run unless the report passes `verdict`, the gate's own test, which the Release's gate reads too.

Nothing a step prints is of a case, a Result or the home: counts and codes alone. A step that fails prints one code and
exits 1, and no traceback, which could quote a case, reaches the log. Results and cases stay in the scratch directory;
only `eval-report.json`, of hashes, verdicts and codes, is written where the upload finds it."""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import sys

from tools import eval_result
from tools.jsonschema_lite import SchemaError, validate

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
SET = pathlib.Path("evals") / "pr-review" / "cases.json"
REPORT = "eval-report.json"
RELEASE = re.compile(r"factory/v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
COMMIT = re.compile(r"[0-9a-f]{40}")
PASS = "pass"


class Stop(Exception):
    """A step that cannot go on, by its code alone."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _errors(document, kind: str) -> list:
    known = eval_result.schemas(ROOT)
    try:
        return validate(document, known[kind], schemas=known)
    except (SchemaError, KeyError):
        return ["no schema"]


def manifest(root: pathlib.Path) -> tuple:
    """`(manifest, sha256 of its bytes)`, the set at the commit checked out, held to `eval-set/1`; Stop otherwise."""
    try:
        data = (root / SET).read_bytes()
        found = json.loads(data.decode("utf-8"))
    except (OSError, ValueError):
        raise Stop("eval_set_unreadable") from None
    if _errors(found, "eval-set") or found["count"] != len(found["cases"]) or \
            len({c["id"] for c in found["cases"]}) != len(found["cases"]):
        raise Stop("eval_set_unreadable")
    return found, hashlib.sha256(data).hexdigest()


def scratch(env: dict, workspace: pathlib.Path) -> pathlib.Path:
    """The directory the cases and Results are kept in: `heldout` under the runner's own temporary directory, which
    must be outside the workspace, so that nothing the upload or a checkout reads can hold a case."""
    temp = env.get("RUNNER_TEMP")
    if not isinstance(temp, str) or not os.path.isabs(temp):
        raise Stop("scratch_unreadable")
    inside, place = os.path.realpath(str(workspace)), os.path.realpath(os.path.join(temp, "heldout"))
    if place == inside or place.startswith(inside + os.sep) or inside.startswith(place + os.sep):
        raise Stop("scratch_in_workspace")
    return pathlib.Path(place)


def _read(path: pathlib.Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise Stop("scratch_unreadable") from None


def _write(path: pathlib.Path, document) -> None:
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def plan(env: dict, root: pathlib.Path, workspace: pathlib.Path) -> str:
    """What the run judges, kept for the steps after it: the Release the dispatch names, the commit checked out, and
    the set by its count and hash. A set of no case is `eval_set_empty`, and the run ends before anything is minted."""
    release, commit = env.get("RELEASE"), env.get("GITHUB_SHA")
    if not (isinstance(release, str) and RELEASE.fullmatch(release)):
        raise Stop("release_unreadable")
    if not (isinstance(commit, str) and COMMIT.fullmatch(commit)):
        raise Stop("commit_unreadable")
    found, digest = manifest(root)
    if found["count"] == 0:
        raise Stop("eval_set_empty")
    place = scratch(env, workspace)
    try:
        place.mkdir(mode=0o700)
        (place / "cases").mkdir(mode=0o700)
    except OSError:
        raise Stop("scratch_unreadable") from None
    _write(place / "plan.json", {"release": release, "commit": commit, "role": found["role"], "intent": found["intent"],
                                 "set": {"count": found["count"], "sha256": digest}})
    return "planned %d cases" % found["count"]


def _planned(env: dict, root: pathlib.Path, workspace: pathlib.Path) -> tuple:
    """`(plan, manifest, scratch)`, the set as `plan` hashed it: a set changed since is no set of this run."""
    place = scratch(env, workspace)
    kept = _read(place / "plan.json")
    found, digest = manifest(root)
    if not isinstance(kept, dict) or kept.get("set") != {"count": found["count"], "sha256": digest}:
        raise Stop("eval_set_changed")
    return kept, found, place


def fetch(env: dict, root: pathlib.Path, workspace: pathlib.Path, transport) -> str:
    """Each case the set names, read from the home into the scratch directory as the bytes its manifest hashed, and
    why each that is not there is not: `fetched.json`, by id, a code or null."""
    from adapters import heldout
    _, found, place = _planned(env, root, workspace)
    try:
        read = heldout.cases(transport, env.get("HELDOUT_OWNER"), env.get("HELDOUT_REPO"), found)
    except Exception:
        raise Stop("unanswered") from None
    why = {}
    for entry, data, code in read:
        why[entry["id"]] = code
        if data is not None:
            path = place / "cases" / ("%s.json" % entry["id"])
            with open(os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as out:
                out.write(data)
    _write(place / "fetched.json", why)
    return "fetched %d of %d cases" % (len([c for c in why.values() if c is None]), found["count"])


def assess(found: dict, why: dict, place: pathlib.Path, review) -> dict:
    """`{id: (verdict, reasons)}` for every case the set names: one not fetched is `unreadable` by its fetch's code;
    one that is no `eval-case/1` of this set's Role and Intent is `unreadable`, `not_this_set`; every other is given to
    `review`, which returns its `result/1`, and scored against the case by `tools/eval_result.py`."""
    assessed = {}
    for entry in found["cases"]:
        code = why.get(entry["id"], "not_found") if isinstance(why, dict) else "not_found"
        if code is not None:
            assessed[entry["id"]] = ("unreadable", [code if code in eval_result_codes() else "unanswered"])
            continue
        try:
            case = json.loads((place / "cases" / ("%s.json" % entry["id"])).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            assessed[entry["id"]] = ("unreadable", ["schema"])
            continue
        if _errors(case, "eval-case") or case["id"] != entry["id"] or \
                (case["role"], case["intent"]) != (found["role"], found["intent"]):
            assessed[entry["id"]] = ("unreadable", ["not_this_set"])
            continue
        said = eval_result.score(case, review(case))
        assessed[entry["id"]] = (said["verdict"], list(dict.fromkeys(said["reasons"])))
    return assessed


def eval_result_codes() -> set:
    """Every reason `eval-report/1` may carry, read from its schema."""
    known = eval_result.schemas(ROOT)
    return set(known["eval-report"]["properties"]["cases"]["items"]["properties"]["reasons"]["items"]["enum"])


def report(kept: dict, found: dict, assessed: dict) -> dict:
    """The `eval-report/1` of this run: the plan's Release, commit and set, and each case by id and hash, in the
    manifest's order, with its verdict and codes."""
    cases = [{"id": e["id"], "sha256": e["sha256"], "verdict": assessed[e["id"]][0], "reasons": assessed[e["id"]][1]}
             for e in found["cases"]]
    return {"schema": "eval-report/1", "release": kept["release"], "commit": kept["commit"], "role": found["role"],
            "intent": found["intent"], "set": dict(kept["set"]), "cases": cases,
            "passed": len([c for c in cases if c["verdict"] == PASS])}


def verdict(document, found: dict, digest: str, commit: str, release: str) -> str:
    """`pass` only for the report of this set on this commit for this Release, with a case at least, every case the
    manifest names once by its id and hash, each passed; otherwise the one code that says why not. The Release's gate
    reads the report it downloads with this function too (the ruling on issue 197, 4″)."""
    if _errors(document, "eval-report"):
        return "report_unreadable"
    if document["commit"] != commit:
        return "another_commit"
    if document["release"] != release:
        return "another_release"
    if (document["role"], document["intent"], document["set"]) != \
            (found["role"], found["intent"], {"count": found["count"], "sha256": digest}):
        return "another_set"
    if found["count"] == 0:
        return "eval_set_empty"
    named = sorted((c["id"], c["sha256"]) for c in found["cases"])
    if sorted((c["id"], c["sha256"]) for c in document["cases"]) != named:
        return "cases_differ"
    if any(c["verdict"] != PASS or c["reasons"] for c in document["cases"]):
        return "case_failed"
    if document["passed"] != found["count"]:
        return "count_differs"
    return PASS


def score(env: dict, root: pathlib.Path, workspace: pathlib.Path, review) -> str:
    """The `run` step's work, given the review Intent as `review`: every case assessed, and the report written where
    the upload finds it, whatever the verdicts, so that a set that fails is uploaded too and `judge` fails the run."""
    kept, found, place = _planned(env, root, workspace)
    assessed = assess(found, _read(place / "fetched.json"), place, review)
    written = report(kept, found, assessed)
    _write(workspace / REPORT, written)
    return "scored %d of %d cases, %d passed" % (len(assessed), found["count"], written["passed"])


def judge(env: dict, root: pathlib.Path, workspace: pathlib.Path) -> str:
    """The run's verdict on its own report: `verdict`'s, which must be `pass`."""
    kept, found, _ = _planned(env, root, workspace)
    try:
        written = json.loads((workspace / REPORT).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise Stop("report_unreadable") from None
    said = verdict(written, found, kept["set"]["sha256"], env.get("GITHUB_SHA"), kept["release"])
    if said != PASS:
        raise Stop(said)
    return "passed %d of %d cases" % (found["count"], found["count"])


def main(step, *given) -> int:
    """One step of the job, run in the workspace: what it says on success, or its one code on failure, and nothing
    else. Whatever it raised is never printed, since its message could quote a case."""
    try:
        said = step(dict(os.environ), ROOT, pathlib.Path.cwd(), *given)
    except Stop as stop:
        print(stop.code)
        return 1
    except Exception:       # a message or a traceback could quote a case or name the home: a code alone
        print("eval_step_failed")
        return 1
    print(said)
    return 0


def exit_with(step, *given) -> None:
    sys.exit(main(step, *given))
