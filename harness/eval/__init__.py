"""The eval job, `factory / eval` (design §4.9 and §3.14, issue 309): the review Intent's held-out set, run on the commit
it judges and scored against its rubric, so that what is measured is what runs. Its steps are modules of their own,
each a `run:` line of `.github/workflows/eval.yml`, in this order:

- `plan` reads the set's manifest at the commit and the Release the dispatch names; a set of no case ends the run here,
  `eval_set_empty`, before any credential is used (ruling 8);
- `fetch` reads each case from the private home through `adapters/heldout.py`, with the Maintainer's read-only token, into
  a scratch directory outside the workspace, on a runner thrown away when the job ends;
- `run` gives each case to the review Intent, its Task built and its Engine called by the functions a live Run's are
  (`harness/task.from_admission`, `harness/run.answer`), and scores its Result with `tools/eval_result.py`;
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
import time

from tools import eval_result
from tools.jsonschema_lite import SchemaError, validate

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
SET = pathlib.Path("evals") / "pr-review" / "cases.json"
REPORT = "eval-report.json"
RELEASE = re.compile(r"factory/v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
COMMIT = re.compile(r"[0-9a-f]{40}")
PASS = "pass"
CASE_FAILED = "case_failed"
# How many cases of each kind a set must hold, those that expect a Finding and those of a criterion met: issue 183's split,
# held here, where the cases are, since the repo cannot hold a count of them true (decision 0099).
KIND_LEAST = 20


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
    except OSError:
        raise Stop("eval_set_unreadable") from None
    return held(data)


def held(data: bytes) -> tuple:
    """`(manifest, sha256 of its bytes)` from the set's bytes, however they were read: the Release's gate reads them at
    the commit it judges, through the transport. Held to `eval-set/1`; Stop otherwise."""
    try:
        found = json.loads(data.decode("utf-8"))
    except (ValueError, AttributeError, RecursionError):
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


NAME = re.compile(r"[a-z0-9][a-z0-9-]*(\.json)?")


def within(directory, name: str) -> str:
    """The path of the file `name` in `directory`, held there: a name of one part, no dot but its extension and no
    slash, that resolves inside the directory itself. Anything else is no file the job reads or writes."""
    base = os.path.realpath(str(directory))
    path = os.path.realpath(os.path.join(base, name)) if isinstance(name, str) and NAME.fullmatch(name) else None
    if path is None or not path.startswith(base + os.sep):
        raise Stop("path_outside")
    return path


def _read(directory, name: str):
    path = within(directory, name)
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        raise Stop("scratch_unreadable") from None


def _write(directory, name: str, document) -> None:
    path = within(directory, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(document, indent=2, sort_keys=True) + "\n")


def plan(env: dict, root: pathlib.Path, workspace: pathlib.Path) -> str:
    """What the run judges, kept for the steps after it: the Release the dispatch names, the commit checked out, and
    the set by its count and hash. A set of no case is `eval_set_empty`, and the run ends before anything is read."""
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
    # When the plan was made, the job's own start to within its checkout: the run step's time is counted from it, so
    # that the fetch and the install spend it too (the run step's BUDGET).
    _write(place, "plan.json", {"release": release, "commit": commit, "role": found["role"], "intent": found["intent"],
                                 "set": {"count": found["count"], "sha256": digest}, "planned_at": now()})
    return "planned %d cases" % found["count"]


def now() -> int:
    """The runner's clock, in whole seconds since the epoch: the one clock every step of the job reads alike."""
    return int(time.time())


def _planned(env: dict, root: pathlib.Path, workspace: pathlib.Path) -> tuple:
    """`(plan, manifest, scratch)`, the set as `plan` hashed it: a set changed since is no set of this run."""
    place = scratch(env, workspace)
    kept = _read(place, "plan.json")
    found, digest = manifest(root)
    if not isinstance(kept, dict) or kept.get("set") != {"count": found["count"], "sha256": digest}:
        raise Stop("eval_set_changed")
    return kept, found, place


def fetch(env: dict, root: pathlib.Path, workspace: pathlib.Path, transport) -> str:
    """Each case the set names, read from the home into the scratch directory as the bytes its manifest hashed, and
    why each that is not there is not: `fetched.json`, by id, a code or null."""
    from adapters import heldout
    _, found, place = _planned(env, root, workspace)
    why = {}
    # Each case is written as it is read, so that no more than one is held at a time, whatever the set's count.
    for entry in found["cases"]:
        try:
            data, code = heldout.case(transport, env.get("HELDOUT_OWNER"), env.get("HELDOUT_REPO"), found["role"], entry)
        except Exception:
            data, code = None, "unanswered"
        why[entry["id"]] = code
        if data is not None:
            path = within(place / "cases", "%s.json" % entry["id"])
            with open(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as out:
                out.write(data)
    _write(place, "fetched.json", why)
    return "fetched %d of %d cases" % (len([c for c in why.values() if c is None]), found["count"])


def assess(found: dict, why: dict, place: pathlib.Path, review) -> dict:
    """`{id: (verdict, reasons)}` for every case the set names: one not fetched is `unreadable` by its fetch's code;
    one that is no `eval-case/1` of this set's Role and Intent is `unreadable`, `not_this_set`; every other is given to
    `review`, which returns its `result/1`, and scored against the case by `tools/eval_result.py`."""
    assessed, interrupted = {}, False
    for entry in found["cases"]:
        code = why.get(entry["id"], "not_found") if isinstance(why, dict) else "not_found"
        if interrupted:
            # An interrupt asks nothing more of the model: every case after it is unanswered, and the report is written.
            code = "unanswered"
        if code is not None:
            assessed[entry["id"]] = ("unreadable", [code if code in eval_result_codes() else "unanswered"])
            continue
        try:
            with open(within(place / "cases", "%s.json" % entry["id"]), encoding="utf-8") as f:
                case = json.load(f)
        except (OSError, ValueError, Stop):
            assessed[entry["id"]] = ("unreadable", ["schema"])
            continue
        if _errors(case, "eval-case") or case["id"] != entry["id"] or \
                (case["role"], case["intent"]) != (found["role"], found["intent"]):
            assessed[entry["id"]] = ("unreadable", ["not_this_set"])
            continue
        # A case the review cannot be asked of, or not in time, is unreadable by its code; whatever else the review
        # raised is unanswered, so that one case's fault leaves the report whole and the run failed.
        try:
            result = review(case)
        except Stop as stop:
            assessed[entry["id"]] = ("unreadable", [stop.code if stop.code in eval_result_codes() else "unanswered"])
            continue
        except Exception:
            assessed[entry["id"]] = ("unreadable", ["unanswered"])
            continue
        except BaseException:
            interrupted = True
            assessed[entry["id"]] = ("unreadable", ["unanswered"])
            continue
        said = eval_result.score(case, result)
        # What the scorer says of a case that did not pass could tell anyone who reads the report the category, severity
        # or place it expects, which are its content, and the report is public. It is one code, the same whatever the
        # scorer said, and the scorer's own codes never leave this step (decisions 0078 and 0099).
        assessed[entry["id"]] = (PASS, []) if said["verdict"] == PASS and not said["reasons"] else ("fail", [CASE_FAILED])
    return assessed


def eval_result_codes() -> set:
    """Every reason `eval-report/1` may carry, read from its schema."""
    known = eval_result.schemas(ROOT)
    return set(known["eval-report"]["properties"]["cases"]["items"]["properties"]["reasons"]["items"]["enum"])


def split_ok(found: dict, place: pathlib.Path):
    """Whether the set's cases, as fetched into the scratch, hold KIND_LEAST of each kind: one word of the whole set,
    never how many of either: the gate needs no more (decision 0099). None where a case was not read, or its answer is no
    kind: such a run fails by that case."""
    counted = {"finding": 0, "met": 0}
    for entry in found["cases"]:
        try:
            case = _read(place / "cases", "%s.json" % entry["id"])
        except Stop:
            return None
        said = case.get("expected") if isinstance(case, dict) else None
        said = said.get("verdict") if isinstance(said, dict) else None
        if not isinstance(said, str) or said not in counted:
            return None
        counted[said] += 1
    return min(counted.values()) >= KIND_LEAST


def report(kept: dict, found: dict, assessed: dict, held: bool = None) -> dict:
    """The `eval-report/1` of this run: the plan's Release, commit and set, each case by id and hash, in the manifest's
    order, with its verdict and codes, and whether the set holds `split_ok`'s kinds."""
    cases = [{"id": e["id"], "sha256": e["sha256"], "verdict": assessed[e["id"]][0], "reasons": assessed[e["id"]][1]}
             for e in found["cases"]]
    return {"schema": "eval-report/1", "release": kept["release"], "commit": kept["commit"], "role": found["role"],
            "intent": found["intent"], "set": dict(kept["set"]), "cases": cases,
            "passed": len([c for c in cases if c["verdict"] == PASS]), "split_ok": held}


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
    if document["split_ok"] is not True:
        return "eval_split_short"
    return PASS


def score(env: dict, root: pathlib.Path, workspace: pathlib.Path, review) -> str:
    """The `run` step's work, given the review Intent as `review`: every case assessed, and the report written where
    the upload finds it, whatever the verdicts, so that a set that fails is uploaded too and `judge` fails the run."""
    kept, found, place = _planned(env, root, workspace)
    assessed = assess(found, _read(place, "fetched.json"), place, review)
    written = report(kept, found, assessed, split_ok(found, place))
    _write(workspace, REPORT, written)
    return "scored %d of %d cases, %d passed" % (len(assessed), found["count"], written["passed"])


def judge(env: dict, root: pathlib.Path, workspace: pathlib.Path) -> str:
    """The run's verdict on its own report: `verdict`'s, which must be `pass`."""
    kept, found, _ = _planned(env, root, workspace)
    try:
        with open(within(workspace, REPORT), encoding="utf-8") as f:
            written = json.load(f)
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
    except BaseException:   # a message or a traceback could quote a case or name the home: a code alone, even for an
        print("eval_step_failed")   # interrupt, whose default report would print what it was chained to
        return 1
    print(said)
    return 0


def exit_with(step, *given) -> None:
    sys.exit(main(step, *given))
