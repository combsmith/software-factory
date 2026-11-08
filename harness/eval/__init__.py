"""The eval job, `factory / eval` (design §4.9 and §3.14, issue 309): the review Intent's held-out set, run on the commit
it judges and scored against its rubric, so that what is measured is what runs. Its steps are modules of their own,
each a `run:` line of `.github/workflows/eval.yml`, in this order:

- `plan` reads the manifest of the set the dispatch names, `evals/<set>/cases.json`, at the commit, and the Release it
  names; a set of no case ends the run here, `eval_set_empty`, before any credential is used (ruling 8);
- `fetch` reads each case from the private home through `adapters/heldout.py`, with the Maintainer's read-only token, into
  a scratch directory outside the workspace, on a runner thrown away when the job ends, and each case's head, the
  commit its diff was taken at, as its tarball with no credential, unpacked by hand beside it (decision 0138);
- `run` gives each case to the review Intent, its Task built and its Engine called by the functions a live Run's are
  (`harness/task.from_admission`, `harness/run.answer`), and scores its Result with `tools/eval_result.py`;
- `seal`, for a gate set alone, encrypts the ledger `run` left in the scratch to the Maintainer's certificates (issue 612);
- `judge` fails the run unless the report passes `verdict`, the gate's own test, which the Release's gate reads too: each
  kind's bar of decision 0150, and no fault of the Engine or the run (decision 0120).

Nothing a step prints is of a case, a Result or the home: counts and codes alone. A step that fails ends on one code and
exits 1, the judge's count of the report's codes before it, and no traceback, which could quote a case, reaches the
log. Results and cases stay in the scratch directory;
only `eval-report.json`, of hashes, verdicts, codes and each unanswered case's cause, held to a shape with no words
(decision 0131), is written where the upload finds it.

A set's manifest says whether it is a gate set (issue 612). A development set's report is `eval-report/1`, each case
by its id. A gate set's is `eval-aggregate/1`, of counts alone, with no case id, per-case verdict or a case's code,
since per-case outcomes under stable ids are what a prompt could be fitted to; each case's outcome, with its Result, is
the ledger, kept in the scratch for `seal` and never uploaded but sealed."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import pathlib
import re
import shutil
import sys
import time

from tools import eval_result
from tools.jsonschema_lite import SchemaError, validate

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
# The sets a dispatch may name: `evals/<set>/cases.json`, the name one part (issue 612). The Release's gate reads the
# review Intent's, SET.
SETS, DEFAULT_SET = pathlib.Path("evals"), "pr-review"
SET_NAME = re.compile(r"[a-z0-9][a-z0-9-]*")
SET = SETS / DEFAULT_SET / "cases.json"
REPORT = "eval-report.json"
AGGREGATE = "eval-aggregate/1"
LEDGER = "ledger.json"
Z = 1.959964                # a Wilson interval's, at 95%
# The fewest cases a gate set may mark natural, or not, where it marks any: a group of one would tell its case's verdict
# by its count, under the case's public id (issue 612, the security read).
ORIGIN_LEAST = 10
RELEASE = re.compile(r"factory/v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
COMMIT = re.compile(r"[0-9a-f]{40}")
PASS = "pass"
# The bar each kind's cases must clear, as whole fractions so that a boundary is exact: those of a criterion met, the clean
# cases, and those that expect a Finding. A guard against regression, set under the measured recall so that a run's noise
# alone does not close it, and raised as recall rises. The set's own share has no bar but the fewest passes these imply,
# `least_passed` (decision 0150, in place of 0120's bar). A case not passed is not passed, whatever it reads as.
BAR_OF_A_KIND = {"met": (9, 10), "finding": (3, 10)}
# How many cases of each kind a set must hold, those that expect a Finding and those of a criterion met: issue 183's split,
# held here, where the cases are, since the repo cannot hold a count of them true (decision 0120).
KIND_LEAST = 20
KINDS = ("finding", "met")
BLOCKING = "blocking"       # whether every case that expects a Finding of this severity passed is said, and closes nothing
BLOCKING_LEAST = 1          # by itself (decision 0150); a set holds one, or a true word for them could mean none exist
# What a case's `cause` may say, each held to a shape that holds no words: an exception's class, the last line of this
# repo's own code it passed, a code, and the CLI's subtype and exit. Never a message, which could quote a case.
CLASS = re.compile(r"[A-Z][A-Za-z0-9_]{0,63}")
AT = re.compile(r"(?:adapters|controller|harness|kernel|release|tools)/[a-z0-9_/]+\.py:[1-9][0-9]{0,5}")
WORD = re.compile(r"[a-z][a-z_]{0,63}")
# The subtypes a cause may name, as the CLI gives them at the pin (`trials/P-13.ended.json`, and the vendor's error of a
# run that failed): any other is `other`, so that whatever a later pin echoes there is never words (the security pass).
SUBTYPES = ("success", "error_during_execution", "error_max_turns", "error_max_structured_output_retries",
            "error_max_budget_usd")


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


def manifest(root: pathlib.Path, name: str = DEFAULT_SET) -> tuple:
    """`(manifest, sha256 of its bytes)`, the set `name` at the commit checked out, held to `eval-set/1`; Stop otherwise,
    as for a name of more than one part."""
    if not (isinstance(name, str) and SET_NAME.fullmatch(name)):
        raise Stop("eval_set_unreadable")
    try:
        data = (root / SETS / name / "cases.json").read_bytes()
    except OSError:
        raise Stop("eval_set_unreadable") from None
    return held(data)


def held(data: bytes) -> tuple:
    """`(manifest, sha256 of its bytes)` from the set's bytes, however they were read: the Release's gate reads them at
    the commit it judges, through the transport. Held to `eval-set/1`, and a gate set to saying of each case whether it
    is natural; Stop otherwise."""
    try:
        found = json.loads(data.decode("utf-8"))
    except (ValueError, AttributeError, RecursionError):
        raise Stop("eval_set_unreadable") from None
    if _errors(found, "eval-set") or found["count"] != len(found["cases"]) or \
            len({c["id"] for c in found["cases"]}) != len(found["cases"]) or \
            (gate_set(found) and not all("natural" in c for c in found["cases"])):
        raise Stop("eval_set_unreadable")
    natural = len([c for c in found["cases"] if c.get("natural") is True])
    if gate_set(found) and any(0 < group < ORIGIN_LEAST for group in (natural, found["count"] - natural)):
        raise Stop("eval_set_unreadable")
    return found, hashlib.sha256(data).hexdigest()


def gate_set(found: dict) -> bool:
    """Whether a manifest is a gate set's, whose report is of counts alone (issue 612): one that says so. A set that does
    not is a development set, as every set was before."""
    return found.get("gate") is True


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
    except (OSError, ValueError, RecursionError):
        raise Stop("scratch_unreadable") from None


def _write(directory, name: str, document) -> None:
    path = within(directory, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(document, indent=2, sort_keys=True) + "\n")


def plan(env: dict, root: pathlib.Path, workspace: pathlib.Path) -> str:
    """What the run judges, kept for the steps after it: the Release the dispatch names, the commit checked out, and
    the set it names, `EVAL_SET`, the review Intent's where none is given, by its name, count and hash. A set of no case
    is `eval_set_empty`, and the run ends before anything is read."""
    release, commit, name = env.get("RELEASE"), env.get("GITHUB_SHA"), env.get("EVAL_SET", DEFAULT_SET)
    if not (isinstance(release, str) and RELEASE.fullmatch(release)):
        raise Stop("release_unreadable")
    if not (isinstance(commit, str) and COMMIT.fullmatch(commit)):
        raise Stop("commit_unreadable")
    found, digest = manifest(root, name)
    if found["count"] == 0:
        raise Stop("eval_set_empty")
    held_out(root, name, found)
    place = scratch(env, workspace)
    try:
        place.mkdir(mode=0o700)
        (place / "cases").mkdir(mode=0o700)
    except OSError:
        raise Stop("scratch_unreadable") from None
    # When the plan was made, the job's own start to within its checkout: the run step's time is counted from it, so
    # that the fetch and the install spend it too (the run step's BUDGET).
    _write(place, "plan.json", {"release": release, "commit": commit, "role": found["role"], "intent": found["intent"],
                                 "name": name, "set": {"count": found["count"], "sha256": digest}, "planned_at": now()})
    return "planned %d cases" % found["count"]


def held_out(root: pathlib.Path, name: str, found: dict) -> None:
    """Stop, `eval_set_overlaps_a_gate_set`, where a set other than a gate set names a case of one, by its id or its
    hash: its report, case by case, would tell what the gate set's keeps back. Every other manifest under `evals/` is
    read, and one that cannot be read stops the run too."""
    if gate_set(found):
        return
    mine = {c["id"] for c in found["cases"]} | {c["sha256"] for c in found["cases"]}
    for other in sorted((root / SETS).glob("*/cases.json")):
        if other.parent.name == name:
            continue
        theirs, _ = manifest(root, other.parent.name)
        if gate_set(theirs) and mine & ({c["id"] for c in theirs["cases"]} | {c["sha256"] for c in theirs["cases"]}):
            raise Stop("eval_set_overlaps_a_gate_set")


def now() -> int:
    """The runner's clock, in whole seconds since the epoch: the one clock every step of the job reads alike."""
    return int(time.time())


def _planned(env: dict, root: pathlib.Path, workspace: pathlib.Path) -> tuple:
    """`(plan, manifest, scratch)`, the set as `plan` hashed it: a set changed since is no set of this run."""
    place = scratch(env, workspace)
    kept = _read(place, "plan.json")
    if not isinstance(kept, dict):
        raise Stop("eval_set_changed")
    found, digest = manifest(root, kept.get("name"))
    if kept.get("set") != {"count": found["count"], "sha256": digest}:
        raise Stop("eval_set_changed")
    return kept, found, place


def cause_of(err: BaseException) -> dict:
    """Why a case raised, as `eval-report/1`'s `cause` holds it: the exception's class, and the last line of this repo's
    code outside its tests that it passed through. Never its message, which could quote a case or the model (issue 309)."""
    said, at = {}, None
    if CLASS.fullmatch(type(err).__name__):
        said["exception"] = type(err).__name__
    step = err.__traceback__
    while step is not None:
        try:
            place = "%s:%d" % (pathlib.Path(step.tb_frame.f_code.co_filename).resolve().relative_to(ROOT).as_posix(),
                               step.tb_lineno)
        except ValueError:
            place = ""
        at = place if AT.fullmatch(place) else at
        step = step.tb_next
    if at is not None:
        said["at"] = at
    return said


def seen_of(review) -> dict:
    """What the CLI said of the last case `review` asked, where it watched the call: its subtype and its exit, or that it
    timed out; each held to its shape, or left out."""
    seen = getattr(review, "seen", None)
    if not isinstance(seen, dict):
        return {}
    said = {}
    if isinstance(seen.get("subtype"), str):
        said["subtype"] = seen["subtype"] if seen["subtype"] in SUBTYPES else "other"
    # A call that could not be made says the class of what it raised.
    if isinstance(seen.get("raised"), str) and CLASS.fullmatch(seen["raised"]):
        said["exception"] = seen["raised"]
    if type(seen.get("exit")) is int and -255 <= seen["exit"] <= 255:
        said["exit"] = seen["exit"]
    if seen.get("timed_out") is True:
        said["timed_out"] = True
    return said


def head_of(data: bytes, place: pathlib.Path, ident: str, transport):
    """The head a case names, its tarball read through `transport` and unpacked into `heads/` under its id, or the code
    `head_unreadable` when it cannot be read or unpacked whole; None, and nothing read, for a case with no head to read,
    which its schema refuses after (decision 0138). Nothing of the head is printed or kept but its files there."""
    from harness import head
    try:
        case = json.loads(data)
        repo, sha = case["facts"]["item"]["repo"], case["head"]
    except (ValueError, TypeError, KeyError, RecursionError):
        return None
    if not (isinstance(sha, str) and COMMIT.fullmatch(sha) and isinstance(repo, str)):
        return None
    folder = place / "heads"
    folder.mkdir(mode=0o700, exist_ok=True)
    try:
        head.unpack(head.fetch(transport, repo, sha), sha, within(folder, ident))
    except (head.Refused, OSError, Stop):
        shutil.rmtree(str(folder / ident), ignore_errors=True)
        return "head_unreadable"
    return None


def fetch(env: dict, root: pathlib.Path, workspace: pathlib.Path, transport, heads=None) -> str:
    """Each case the set names, read from the home into the scratch directory as the bytes its manifest hashed, and
    why each that is not there is not: `fetched.json`, by id, a code or null, and `fetch-causes.json`, by id, what a read
    that raised raised, by its class and place alone. Each case's head is read through `heads`, with no credential, and
    a case whose head cannot be read whole is not there either, `head_unreadable`."""
    from adapters import heldout
    _, found, place = _planned(env, root, workspace)
    why, causes = {}, {}
    # Each case is written as it is read, so that no more than one is held at a time, whatever the set's count.
    for entry in found["cases"]:
        try:
            data, code = heldout.case(transport, env.get("HELDOUT_OWNER"), env.get("HELDOUT_REPO"), found["role"], entry)
        except Exception as err:
            data, code = None, "unanswered"
            causes[entry["id"]] = cause_of(err)
        if data is not None and heads is not None:
            code = head_of(data, place, entry["id"], heads)
        why[entry["id"]] = code
        if data is not None and code is None:
            path = within(place / "cases", "%s.json" % entry["id"])
            with open(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as out:
                out.write(data)
    _write(place, "fetched.json", why)
    _write(place, "fetch-causes.json", causes)
    return "fetched %d of %d cases" % (len([c for c in why.values() if c is None]), found["count"])


# The reasons of a failed Result that say the model gave no answer, by the Engine's fault or the Factory's: never the
# reviewer's. `result_invalid` stays the reviewer's: an answer that could not be held to its schema (decision 0121).
ENGINE_FAULTS = ("credential_missing", "engine_version", "engine_model", "engine_failed", "engine_timeout", "task_too_large",
                 "rubric_unreadable", "no_answer", "head_unreadable")
# What stops a run reaching or trusting a case, whatever the rest of the set read: no bar can be held over it. A case's own
# fault is another matter, one case not passed, which is the bar's to weigh (decision 0120).
RUN_FAULTS = ("schema", "not_found", "hash_differs", "too_large", "unanswered")


# What facts/1 has required since the review Intent's set was made, at d556992, each with what the job gives a case that
# lacks it, and what that means. The set stays as it is, and a case cannot exercise one of these until it is issued again
# with it. Applied to a case's facts alone, in this job alone, before anything reads them; the live path never fills.
# A field made required later fails tests/test_evals.py::test_the_facts_the_set_was_made_with_read_as_todays_once_filled
# until it has a row here, or the set is issued again (decision 0105).
FACTS_THE_SET_PREDATES = (
    ("last_reopened_at", None, "never reopened: a case cannot exercise an approval from before a reopening"),
    ("expired_reviews", [], "no Lens review past retention: a case cannot exercise one being asked for again"),
    ("description_edited_at", None, "never edited: a case cannot exercise an edit of the description after the approval"),
)
THREAD_FIELDS_THE_SET_PREDATES = (
    ("ruling", None, "the Lens decided nothing of its Finding: a case cannot exercise a ruling on a thread"),
)


def current_facts(facts):
    """A copy of a case's `facts`, each field the set predates filled by its row where it is absent, and a field the case
    gives kept as it is. What is no facts, or nested past what can be copied, is handed back for the schema to refuse."""
    if not isinstance(facts, dict):
        return facts
    try:
        filled = copy.deepcopy(facts)
    except RecursionError:
        return facts
    for field, default, _ in FACTS_THE_SET_PREDATES:
        filled.setdefault(field, copy.deepcopy(default))
    threads = filled.get("threads")
    for thread in threads if isinstance(threads, list) else []:
        for field, default, _ in THREAD_FIELDS_THE_SET_PREDATES:
            if isinstance(thread, dict):
                thread.setdefault(field, copy.deepcopy(default))
    return filled


def case_fault(case: dict):
    """The code of what would refuse this case's Task, read before it is built, or None: `harness/task.py` refuses each of
    these too, in words a live Run's report needs and this job may not print. Held here so that a set that fails says
    why by a code alone, each its owner's to mend in the home (decision 0105). `case` is a current `eval-case/1`."""
    facts = case["facts"]
    if not all(v is True for v in facts["complete"].values()):
        return "facts_read_short"
    try:
        diff = case["diff"].encode("utf-8")
    except UnicodeEncodeError:
        return "diff_unreadable"
    if not diff:
        return "diff_unreadable"
    if "sha256:" + hashlib.sha256(diff).hexdigest() != facts["content_id"]:
        return "diff_not_content"
    # The Task's text names who pushed it, a login, where facts/1 also allows null or any string.
    source = eval_result.schemas(ROOT)["task"]["properties"]["texts"]["items"]["properties"]["source"]["pattern"]
    if not (isinstance(facts["last_pusher"], str) and re.fullmatch(source, facts["last_pusher"])):
        return "pusher_unnamed"
    # So does the issue's, where the case holds one.
    if "issue" in case and not re.fullmatch(source, case["issue"]["by"]["name"]):
        return "issue_unreadable"
    return None


def assess(found: dict, why: dict, place: pathlib.Path, review, causes: dict = None, alternates: set = None,
           surplus: dict = None, results: dict = None) -> dict:
    """`{id: (verdict, reasons)}` for every case the set names: one not fetched is `unreadable` by its fetch's code;
    the facts of each are filled as `current_facts` says, for all that reads the case after; one whose facts are still no
    `facts/1` is `unreadable`, `facts_not_current`; one that is no `eval-case/1` of this set's Role and Intent is
    `unreadable`, `not_this_set`; one `case_fault` finds a fault in is `unreadable` by that code; one whose expected Finding
    is off its rubric is `unreadable`, `answer_off_rubric`; every other is given to `review`, which returns its `result/1`,
    and scored against the case by `tools/eval_result.py`. What `cause_of` and `seen_of` say of a case unanswered, or
    stopped by the Engine, goes in `causes`, by id, where one is given; the id of each pass the scorer marks
    `at_alternate`, in `alternates` (decision 0143); how many gating Findings the scorer counts away from every
    place a case gives, in `surplus`, by id (issue 610); and each Result the review returned, in `results`, by id, where
    one is given, for a gate set's ledger (issue 612)."""
    assessed, interrupted = {}, False
    causes = {} if causes is None else causes
    alternates = set() if alternates is None else alternates
    surplus = {} if surplus is None else surplus
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
        except (OSError, ValueError, RecursionError, Stop):
            assessed[entry["id"]] = ("unreadable", ["schema"])
            continue
        if isinstance(case, dict) and "facts" in case:
            case = dict(case, facts=current_facts(case["facts"]))
            if _errors(case["facts"], "facts"):
                assessed[entry["id"]] = ("unreadable", ["facts_not_current"])
                continue
        if _errors(case, "eval-case") or case["id"] != entry["id"] or \
                (case["role"], case["intent"]) != (found["role"], found["intent"]):
            assessed[entry["id"]] = ("unreadable", ["not_this_set"])
            continue
        fault = case_fault(case)
        if fault is not None:
            assessed[entry["id"]] = ("unreadable", [fault])
            continue
        # A case whose answer the rubric refuses would reward a Result `apply` refuses: it asks nothing of the model, and
        # says so by a code alone, for its owner to mend in the home (issue 421).
        if eval_result.off_rubric(case):
            assessed[entry["id"]] = ("unreadable", ["answer_off_rubric"])
            continue
        # A case the review cannot be asked of, or not in time, is unreadable by its code; whatever else the review
        # raised is unanswered, so that one case's fault leaves the report whole, for `verdict` to weigh.
        try:
            result = review(case)
        except Stop as stop:
            assessed[entry["id"]] = ("unreadable", [stop.code if stop.code in eval_result_codes() else "unanswered"])
            if stop.code not in eval_result_codes() and isinstance(stop.code, str) and WORD.fullmatch(stop.code):
                causes[entry["id"]] = {"stop": stop.code}
            continue
        except Exception as err:
            assessed[entry["id"]] = ("unreadable", ["unanswered"])
            causes[entry["id"]] = dict(cause_of(err), **seen_of(review))
            continue
        except BaseException as err:
            interrupted = True
            assessed[entry["id"]] = ("unreadable", ["unanswered"])
            causes[entry["id"]] = cause_of(err)
            continue
        if results is not None:
            results[entry["id"]] = result
        if isinstance(result, dict) and result.get("status") == "failed" and result.get("reason") in ENGINE_FAULTS:
            assessed[entry["id"]] = ("unreadable", [result["reason"]])
            causes[entry["id"]] = seen_of(review)
            continue
        said = eval_result.score(case, result)
        # What the scorer says is codes of the report's enum: nothing of a case's content, and no word of the model's. A
        # case's kind is not worth hiding, and a run cannot be read without them (decision 0120).
        assessed[entry["id"]] = (said["verdict"], said["reasons"])
        if said.get("at_alternate") is True:
            alternates.add(entry["id"])
        if said.get("surplus_gating"):
            surplus[entry["id"]] = said["surplus_gating"]
    return assessed


def eval_result_codes() -> set:
    """Every reason `eval-report/1` may carry, read from its schema."""
    known = eval_result.schemas(ROOT)
    return set(known["eval-report"]["properties"]["cases"]["items"]["properties"]["reasons"]["items"]["enum"])


def _expected(found: dict, place: pathlib.Path):
    """`{id: what it expects}` of the set's cases, as fetched into the scratch, or None where a case was not read, or its
    answer is no kind: such a run fails by that case."""
    expected = {}
    for entry in found["cases"]:
        try:
            case = _read(place / "cases", "%s.json" % entry["id"])
        except Stop:
            return None
        said = case.get("expected") if isinstance(case, dict) else None
        kind = said.get("verdict") if isinstance(said, dict) else None
        if not isinstance(kind, str) or kind not in KINDS:
            return None
        expected[entry["id"]] = said
    return expected


def kinds_of(found: dict, place: pathlib.Path):
    """`{id: kind}` of the set's cases, or None where `_expected` can say nothing."""
    expected = _expected(found, place)
    return None if expected is None else {case: said["verdict"] for case, said in expected.items()}


def split_ok(found: dict, place: pathlib.Path):
    """Whether the set's cases hold KIND_LEAST of each kind and BLOCKING_LEAST that expect a blocking Finding: one word of
    the whole set, never how many of any: the gate needs no more (decision 0120). None where `kinds_of` can say nothing."""
    kinds = kinds_of(found, place)
    if kinds is None:
        return None
    return min(list(kinds.values()).count(kind) for kind in KINDS) >= KIND_LEAST \
        and len(blocking_cases(found, _expected(found, place))) >= BLOCKING_LEAST


def _clears(passed: int, of: int, bar: tuple) -> bool:
    """Whether `passed` of `of` is at least the fraction `bar`, in whole numbers, so that exactly on it clears."""
    return passed * bar[1] >= of * bar[0]


def least_passed(count: int, least: int) -> int:
    """The fewest of `count` cases a set can have passed with each kind on its BAR_OF_A_KIND and holding `least` cases at
    least: those `least` of each kind, and every other case in the kind whose bar asks fewest of them (decision 0150). A
    set too small to hold `least` of each kind is read with no least."""
    least = least if count >= least * len(KINDS) else 0
    on = lambda bar, cases: -(-cases * bar[0] // bar[1])        # the fewest of `cases` that clear `bar`, in whole numbers
    return min(sum(on(BAR_OF_A_KIND[kind], count - least * (len(KINDS) - 1) if kind == rest else least) for kind in KINDS)
               for rest in KINDS)


def kinds_pass(found: dict, place: pathlib.Path, assessed: dict):
    """`{kind: whether at least its BAR_OF_A_KIND of its cases passed}`, read where the cases are: one word for each, never
    how many (decisions 0120 and 0150). None where `kinds_of` can say nothing. A kind with no case has nothing to fail: `split_ok`
    holds that."""
    kinds = kinds_of(found, place)
    if kinds is None:
        return None
    said = {}
    for kind in KINDS:
        cases = [case for case, its in kinds.items() if its == kind]
        passed = [case for case in cases if assessed[case] == (PASS, [])]
        said[kind] = _clears(len(passed), len(cases), BAR_OF_A_KIND[kind])
    return said


def _blocking_criteria(role) -> set:
    """The criteria of the rubric `role` reviews by whose Finding is blocking; none where it cannot be read, as a case is
    then off it and is not asked."""
    try:
        rubric = json.loads((ROOT / "config" / ("rubric-%s.json" % role)).read_text())
        return {c["id"] for c in rubric["criteria"] if c["severity_if_violated"] == BLOCKING}
    except (OSError, ValueError, KeyError, TypeError):
        return set()


def blocking_cases(found: dict, expected: dict) -> list:
    """The cases that expect a blocking Finding: by what a case states or by what the rubric gives its criterion, so that
    one off its rubric cannot leave the rule by stating less (decision 0120)."""
    criteria = _blocking_criteria(found.get("role"))
    return [case for case, said in expected.items() if isinstance(said.get("finding"), dict)
            and (said["finding"].get("severity") == BLOCKING or said.get("criterion") in criteria)]


def blocking_pass(found: dict, place: pathlib.Path, assessed: dict):
    """Whether every case that expects a blocking Finding passed, read where the cases are: one word, never how many, which
    the judge's line says and which closes nothing by itself (decision 0150). True of a set with none, which `split_ok`
    closes on. None where `_expected` can say nothing."""
    expected = _expected(found, place)
    if expected is None:
        return None
    return all(assessed[case] == (PASS, []) for case in blocking_cases(found, expected))


def report(kept: dict, found: dict, assessed: dict, held: bool = None, kinds: dict = None, blocking: bool = None,
           causes: dict = None, alternates: set = None, surplus: dict = None) -> dict:
    """The `eval-report/1` of this run: the plan's Release, commit and set, each case by id and hash, in the manifest's
    order, with its verdict and codes and, where one was found, its cause, its mark where it passed at an alternate
    place alone (decision 0143), and how many gating Findings it drew away from every place (issue 610), whether the
    set holds `split_ok`'s kinds,
    whether each cleared its bar, and whether every case that expects a blocking Finding passed."""
    causes, alternates, surplus = causes or {}, alternates or set(), surplus or {}
    cases = [dict({"id": e["id"], "sha256": e["sha256"], "verdict": assessed[e["id"]][0], "reasons": assessed[e["id"]][1]},
                  **({"cause": causes[e["id"]]} if causes.get(e["id"]) else {}),
                  **({"at_alternate": True} if e["id"] in alternates and assessed[e["id"]] == (PASS, []) else {}),
                  **({"surplus_gating": surplus[e["id"]]} if surplus.get(e["id"]) else {}))
             for e in found["cases"]]
    return {"schema": "eval-report/1", "release": kept["release"], "commit": kept["commit"], "role": found["role"],
            "intent": found["intent"], "set": dict(kept["set"]), "cases": cases,
            "passed": len([c for c in cases if c["verdict"] == PASS]), "split_ok": held, "kinds_pass": kinds, "blocking_pass": blocking}


def wilson(passed: int, of: int) -> dict:
    """The Wilson interval at 95% of `passed` of `of`, each end to four places, so that a report's can be held to its
    counts exactly; the whole of [0, 1] for no case."""
    if of == 0:
        return {"low": 0.0, "high": 1.0}
    share, z2 = passed / of, Z * Z
    centre, spread = share + z2 / (2 * of), Z * (share * (1 - share) / of + z2 / (4 * of * of)) ** 0.5
    return {"low": round(max(0.0, (centre - spread) / (1 + z2 / of)), 4),
            "high": round(min(1.0, (centre + spread) / (1 + z2 / of)), 4)}


def ledger_of(kept: dict, found: dict, assessed: dict, causes: dict, alternates: set, results: dict,
              surplus: dict = None) -> dict:
    """The `eval-ledger/1` of a gate set's run: each case as `report` would list it, whether it is natural, and the Result
    the review returned for it, under a salt drawn for this run alone, so that its hash in the report tells nothing of
    what it holds. It stays in the scratch for `seal`, and is never uploaded but sealed (issue 612)."""
    natural = {e["id"]: e.get("natural") is True for e in found["cases"]}
    cases = [dict(case, natural=natural[case["id"]], **({"result": results[case["id"]]} if case["id"] in results else {}))
             for case in report(kept, found, assessed, causes=causes, alternates=alternates, surplus=surplus)["cases"]]
    return {"schema": "eval-ledger/1", "salt": os.urandom(16).hex(), "release": kept["release"], "commit": kept["commit"],
            "role": found["role"], "intent": found["intent"], "set": dict(kept["set"]), "cases": cases}


# What a gate set's report sums of its Results' usage: each a count, and the cost in dollars.
SUMMED = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens", "turns")


def usage_of(results: dict) -> dict:
    """What the Results the review returned spent, summed: how many said, each count, the cost and the seconds. A Result
    whose usage is not whole is left out of every sum, and of the count."""
    said = dict({field: 0 for field in SUMMED}, answered=0, cost_usd=0.0, seconds=0.0)
    for result in results.values():
        usage = result.get("usage") if isinstance(result, dict) else None
        if not isinstance(usage, dict) or not all(type(usage.get(f)) is int and usage[f] >= 0 for f in SUMMED) or \
                not all(type(usage.get(f)) in (int, float) and usage[f] >= 0 for f in ("cost_usd", "seconds")):
            continue
        said["answered"] += 1
        for field in SUMMED + ("cost_usd", "seconds"):
            said[field] += usage[field]
    return dict(said, cost_usd=round(said["cost_usd"], 6), seconds=round(said["seconds"], 3))


def engine_of(role: str) -> dict:
    """What answered, as the checkout pins it: the Engine and its model, and the sha256 of the Role's instructions and of
    its rubric, each null where it cannot be read."""
    def digest(path):
        try:
            return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
        except OSError:
            return None
    try:
        pinned = json.loads((ROOT / "config" / "harness.json").read_text())["engine"]
        name, version, model = pinned["name"], pinned["version"], pinned["model"]
    except (OSError, ValueError, KeyError, TypeError):
        name = version = model = None
    return {"name": name, "version": version, "model": model, "prompt_sha256": digest("roles/%s/prompt.md" % role),
            "rubric_sha256": digest("config/rubric-%s.json" % role)}


def aggregate(kept: dict, found: dict, assessed: dict, place: pathlib.Path, results: dict, ledger: bytes) -> dict:
    """The `eval-aggregate/1` of a gate set's run: counts alone, with no case id, per-case verdict or a case's code (issue
    612). How many passed; of each kind, its cases, its passes and their Wilson interval, null where `kinds_of` can say
    nothing; the natural cases and those that are not, apart; each code of a case not read, by how many; the usage
    summed; what answered; the bars applied; the words `verdict` reads; and the ledger's salted sha256, beside which
    `seal` writes its ciphertext's. Raw counts, so that reports on one commit can be pooled (issue 613)."""
    passed = {case for case, said in assessed.items() if said == (PASS, [])}
    kinds = kinds_of(found, place)
    counted = None if kinds is None else {
        kind: {"cases": n, "passed": p, "interval": wilson(p, n)}
        for kind, n, p in ((k, list(kinds.values()).count(k), len([c for c in passed if kinds[c] == k])) for k in KINDS)}
    natural = {e["id"] for e in found["cases"] if e.get("natural") is True}
    origin = {"natural": natural, "constructed": {e["id"] for e in found["cases"]} - natural}
    codes = [code for verdict_of, reasons in assessed.values() if verdict_of == "unreadable" for code in reasons]
    return {"schema": AGGREGATE, "release": kept["release"], "commit": kept["commit"], "role": found["role"],
            "intent": found["intent"], "set": dict(kept["set"]), "passed": len(passed), "kinds": counted,
            "origin": {name: {"cases": len(ids), "passed": len(ids & passed)} for name, ids in origin.items()},
            "faults": [{"code": code, "count": codes.count(code)} for code in sorted(set(codes))],
            "usage": usage_of(results), "engine": engine_of(found["role"]),
            "bars": {kind: list(BAR_OF_A_KIND[kind]) for kind in KINDS}, "kind_least": KIND_LEAST,
            "split_ok": split_ok(found, place), "kinds_pass": kinds_pass(found, place, assessed),
            "blocking_pass": blocking_pass(found, place, assessed),
            "ledger": {"salted_sha256": hashlib.sha256(ledger).hexdigest()}}


def _judged(document: dict, found: dict, digest: str, commit: str, release: str):
    """The code that says a report is of another commit, Release or set than the one judged, or None."""
    if document["commit"] != commit:
        return "another_commit"
    if document["release"] != release:
        return "another_release"
    if (document["role"], document["intent"], document["set"]) != \
            (found["role"], found["intent"], {"count": found["count"], "sha256": digest}):
        return "another_set"
    if found["count"] == 0:
        return "eval_set_empty"
    return None


def aggregate_verdict(document, found: dict, digest: str, commit: str, release: str) -> str:
    """`verdict`'s word on a gate set's report: `pass` only for an `eval-aggregate/1` of this set on this commit for
    this Release, sealed, with no fault of the Engine or the run, whose counts add up to the set's and to its own words,
    held to the bars applied here, and each kind's bar cleared (decision 0150); otherwise the one code that says why not."""
    if _errors(document, "eval-aggregate"):
        return "report_unreadable"
    judged = _judged(document, found, digest, commit, release)
    if judged is not None:
        return judged
    codes = [fault["code"] for fault in document["faults"]]
    if len(set(codes)) != len(codes) or not set(codes) <= eval_result_codes():
        return "count_differs"
    if set(codes) & set(ENGINE_FAULTS):
        return "engine_fault"
    if set(codes) & set(RUN_FAULTS):
        return "run_fault"
    # Each count is the job's: the natural cases are the manifest's, the passes are the report's own, and no case is
    # both passed and not read. A report whose counts do not add up is not the job's.
    natural, origin, passed = len([e for e in found["cases"] if e.get("natural") is True]), document["origin"], document["passed"]
    if (origin["natural"]["cases"], origin["constructed"]["cases"]) != (natural, found["count"] - natural) \
            or origin["natural"]["passed"] + origin["constructed"]["passed"] != passed \
            or any(o["passed"] > o["cases"] for o in origin.values()) \
            or passed + sum(fault["count"] for fault in document["faults"]) > found["count"]:
        return "count_differs"
    kinds, words = document["kinds"], document["kinds_pass"]
    if (kinds is None) != (words is None):
        return "count_differs"
    # Where no kind could be read, the job says nothing of the split or of the blocking cases either.
    if kinds is None and (document["split_ok"] is not None or document["blocking_pass"] is not None):
        return "count_differs"
    if kinds is not None and (
            sum(kinds[k]["cases"] for k in KINDS) != found["count"] or sum(kinds[k]["passed"] for k in KINDS) != passed
            or any(kinds[k]["passed"] > kinds[k]["cases"] or kinds[k]["interval"] != wilson(kinds[k]["passed"], kinds[k]["cases"])
                   for k in KINDS)
            or words != {k: _clears(kinds[k]["passed"], kinds[k]["cases"], BAR_OF_A_KIND[k]) for k in KINDS}
            or (document["split_ok"] is True and min(kinds[k]["cases"] for k in KINDS) < KIND_LEAST)):
        return "count_differs"
    if document["bars"] != {kind: list(BAR_OF_A_KIND[kind]) for kind in KINDS} or document["kind_least"] != KIND_LEAST:
        return "bars_differ"
    if passed < least_passed(found["count"], KIND_LEAST if document["split_ok"] is True else 0) \
            or (words is not None and not all(words.values())):
        return "case_failed"
    if document["split_ok"] is not True or kinds is None or document["blocking_pass"] is None:
        return "eval_split_short"
    return PASS


def verdict(document, found: dict, digest: str, commit: str, release: str) -> str:
    """`pass` only for the report of this set on this commit for this Release, with a case at least, every case the
    manifest names once by its id and hash, no case stopped by a fault of the Engine or the run, and each kind's
    BAR_OF_A_KIND of its cases passed (decision 0150); otherwise the one code that says why not.
    The Release's gate reads the report it downloads with this function too (the ruling on issue 197, 4″). A gate set's
    report is `aggregate_verdict`'s to judge, and a report of the other kind than its set's is `report_of_another_kind`."""
    said = document.get("schema") if isinstance(document, dict) else None
    if said in (AGGREGATE, "eval-report/1") and (said == AGGREGATE) != gate_set(found):
        return "report_of_another_kind"
    if gate_set(found):
        return aggregate_verdict(document, found, digest, commit, release)
    if _errors(document, "eval-report"):
        return "report_unreadable"
    judged = _judged(document, found, digest, commit, release)
    if judged is not None:
        return judged
    named = sorted((c["id"], c["sha256"]) for c in found["cases"])
    if sorted((c["id"], c["sha256"]) for c in document["cases"]) != named:
        return "cases_differ"
    if any(set(c["reasons"]) & set(ENGINE_FAULTS) for c in document["cases"]):
        return "engine_fault"
    if any(set(c["reasons"]) & set(RUN_FAULTS) for c in document["cases"]):
        return "run_fault"
    # A case is passed by its verdict and no code, and any other names what became of it, as the job writes them; the
    # report's own count must agree, or it is not the job's.
    passed = len([c for c in document["cases"] if c["verdict"] == PASS])
    if any((c["verdict"] == PASS) == bool(c["reasons"]) for c in document["cases"]) or document["passed"] != passed:
        return "count_differs"
    # A case marked as passed at an alternate place alone is a pass (decision 0143).
    if any(c.get("at_alternate") and c["verdict"] != PASS for c in document["cases"]):
        return "count_differs"
    # Each kind is held to its own bar, where the cases are. The set's share is held only to the fewest passes a set
    # whose kinds each cleared could hold, of KIND_LEAST each where the report says the split held, so that a report
    # whose words its own cases cannot bear is not passed. A blocking case not passed closes nothing by itself (decision
    # 0150).
    kinds, blocking = document["kinds_pass"], document["blocking_pass"]
    if passed < least_passed(found["count"], KIND_LEAST if document["split_ok"] is True else 0) \
            or (kinds is not None and not all(kinds.values())):
        return "case_failed"
    if document["split_ok"] is not True or kinds is None or blocking is None:
        return "eval_split_short"
    return PASS


def score(env: dict, root: pathlib.Path, workspace: pathlib.Path, review) -> str:
    """The `run` step's work, given the review Intent as `review`: every case assessed, and the report written where
    the upload finds it, whatever the verdicts, so that a set that fails is uploaded too and `judge` fails the run."""
    kept, found, place = _planned(env, root, workspace)
    try:
        causes = _read(place, "fetch-causes.json")
    except Stop:
        causes = {}
    causes = dict(causes) if isinstance(causes, dict) else {}
    alternates, surplus = set(), {}
    if gate_set(found):
        return written_out(workspace, found, *gate_scored(kept, found, place, review, causes, alternates, surplus))
    assessed = assess(found, _read(place, "fetched.json"), place, review, causes, alternates, surplus)
    written = report(kept, found, assessed, split_ok(found, place), kinds_pass(found, place, assessed),
                     blocking_pass(found, place, assessed), causes, alternates, surplus)
    return written_out(workspace, found, assessed, written)


def written_out(workspace: pathlib.Path, found: dict, assessed: dict, written: dict) -> str:
    """The report written where the upload finds it, and the step's line of counts."""
    _write(workspace, REPORT, written)
    return "scored %d of %d cases, %d passed" % (len(assessed), found["count"], written["passed"])


def gate_scored(kept: dict, found: dict, place: pathlib.Path, review, causes: dict, alternates: set, surplus: dict) -> tuple:
    """`(assessed, report)` of a gate set's run: each case, with its Result, written to the ledger in the scratch, and the
    report of counts alone that binds it (issue 612)."""
    results = {}
    assessed = assess(found, _read(place, "fetched.json"), place, review, causes, alternates, surplus, results)
    ledger = (json.dumps(ledger_of(kept, found, assessed, causes, alternates, results, surplus), indent=2, sort_keys=True)
              + "\n").encode("utf-8")
    with open(os.open(within(place, LEDGER), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as out:
        out.write(ledger)
    return assessed, aggregate(kept, found, assessed, place, results, ledger)


def closed_of(document: dict) -> list:
    """What a report says closed the gate, each kind under its bar, and a blocking case not passed, which does not by
    itself (decision 0150)."""
    closed = ["%s under its bar" % kind for kind, ok in sorted((document["kinds_pass"] or {}).items()) if not ok]
    closed += ["a blocking case not passed"] if document["blocking_pass"] is False else []
    return closed


def tally_of_aggregate(document: dict) -> str:
    """One line of a gate set's report that holds to its schema: how many passed, each code of a case not read by how
    many, and what `closed_of` says. Counts and codes alone, as the report is."""
    return "; ".join(["%d of %d passed" % (document["passed"], document["set"]["count"]),
                      ", ".join("%s %d" % (f["code"], f["count"]) for f in document["faults"]) or "no code"]
                     + closed_of(document))


def tally(document: dict) -> str:
    """One line of a report that holds to its schema: how many cases passed, how many carry each code, each kind under
    its bar, which closes the gate, and a blocking case not passed, which does not by itself (decision 0150), as a share
    alone may not say why, how many passed at an alternate place alone (decision 0143), and how many gating Findings
    were put away from every place a case gives (issue 610). A gate set's report says as much by its counts
    (`tally_of_aggregate`)."""
    if document.get("schema") == AGGREGATE:
        return tally_of_aggregate(document)
    codes = [code for case in document["cases"] for code in case["reasons"]]
    alternate = len([case for case in document["cases"] if case.get("at_alternate") and case["verdict"] == PASS])
    away = sum(case.get("surplus_gating", 0) for case in document["cases"])
    closed = closed_of(document)
    # Each cause by what it says, held to its schema like the rest, with how many cases gave it.
    causes = [" ".join("%s=%s" % (k, v) for k, v in sorted(case["cause"].items())) for case in document["cases"] if case.get("cause")]
    return "; ".join(["%d of %d passed" % (document["passed"], len(document["cases"]))
                      + (", %d at an alternate place" % alternate if alternate else "")
                      + (", %d gating away from the place" % away if away else ""),
                      ", ".join("%s %d" % (code, codes.count(code)) for code in sorted(set(codes))) or "no code"] + closed
                     + ["%s %d" % (c, causes.count(c)) for c in sorted(set(causes))])


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
        # Either comes only once `verdict` has held the report to its schema, so what is printed is the enum's codes,
        # whatever wrote the report. A run that clears the bar says the same line, as its cases not passed still count.
        if said in ("engine_fault", "run_fault", "case_failed"):
            print(tally(written))
        raise Stop(said)
    return tally(written)


def main(step, *given) -> int:
    """One step of the job, run in the workspace: what it says on success, or its one code on failure, and nothing
    else of its own. Whatever it raised is never printed, since its message could quote a case."""
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
