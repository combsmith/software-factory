"""Score one Result against one held-out case: did the review raise the Finding the case expects, or cover the criterion
as met? `python3 -m tools.eval_result CASE RESULT` prints the score and exits 0 on a pass, 1 on a fail and 2 when either
file cannot be read. The case comes from the private home at run time; nothing here reads it from this repo."""
from __future__ import annotations

import json
import os
import pathlib
import sys

from harness import apply, task
from kernel.coverage import readable_rubric
from kernel.gate import GATING_SEVERITIES, SECURITY
from tools.jsonschema_lite import SchemaError, validate

ROOT = pathlib.Path(__file__).resolve().parent.parent
PASS, FAIL, UNREADABLE = "pass", "fail", "unreadable"
EXIT = {PASS: 0, FAIL: 1, UNREADABLE: 2}


def schemas(root: pathlib.Path = ROOT) -> dict:
    return {p.name[: -len(".schema.json")]: json.loads(p.read_text()) for p in sorted((root / "schemas").glob("*.schema.json"))}


# The most lines a raised Finding may span beyond the place it is at: a wider one, or one with no lines, could be at any
# place, and a Role drifting toward broad Findings would score higher while being less use (decision 0143).
SPAN_BEYOND = 15
MISSES = ("category_differs", "severity_differs", "location_differs")
WENT = ("finding_not_raised", "finding_elsewhere", "finding_uncited", "finding_cites_another")


def _lines(location: dict):
    """(first, last) of a location's lines; None where it names none, the whole file; False where they cannot be read:
    an end with no start, or an end before the start."""
    if "start_line" not in location:
        return False if "end_line" in location else None
    first, last = location["start_line"], location.get("end_line", location["start_line"])
    return (first, last) if first <= last else False


def _overlaps(expected: dict, raised: dict) -> bool:
    """Whether a raised Finding's location is at a place the case gives: the same path, and its lines given, spanning no
    more than SPAN_BEYOND lines beyond the place's own, and overlapping them; a place given without lines is the whole
    file. A Finding given without lines, or whose lines cannot be read, is at no place (decision 0143)."""
    if raised.get("path") != expected["path"]:
        return False
    theirs, ours = _lines(raised), _lines(expected)
    if not theirs:
        return False
    if ours is None:
        return True
    return theirs[1] - theirs[0] <= ours[1] - ours[0] + SPAN_BEYOND and theirs[0] <= ours[1] and ours[0] <= theirs[1]


def _places(expected: dict) -> list:
    """Each place the expected Finding may rightly be put: its `location`, then each of `also_at` (decision 0143)."""
    return [expected["location"]] + expected.get("also_at", [])


def _at(expected: dict, raised: dict) -> bool:
    """Whether a raised Finding's location is at any place the expected Finding may rightly be put."""
    return any(_overlaps(place, raised) for place in _places(expected))


def _hunks(diff: str) -> dict:
    """`{path: [lines of each hunk]}`: the lines each hunk of the diff holds on the head's side, by the path its file's
    `+++ b/` header names. A line is one the Task numbered for the model (decision 0137): its row is the diff's own row
    led by its number, so a row that already reads as numbered, outside any hunk, is no line."""
    held, path, hunk = {}, None, set()
    for row, given in zip(task.ROW.findall(diff), task.ROW.findall(task.numbered(diff))):
        if given != row:
            hunk.add(int(given.split(task.SEPARATOR, 1)[0]))
        elif row.startswith("+++ "):
            name = row[len("+++ "):].rstrip("\r\n")
            path = name[len("b/"):] if name.startswith("b/") else None
        elif task.HUNK.match(row):
            hunk = set()
            held.setdefault(path, []).append(hunk)
    return held


def _in_hunks(places: list, diff: str) -> bool:
    """Whether each place's lines, all of them, are lines one hunk of the diff holds on the head's side, in its file
    (decision 0143): an alternate place names a changed line the reviewer was shown, never anywhere else, and one whose
    lines cannot be read names none."""
    held = _hunks(diff)
    for place in places:
        lines = _lines(place)
        if not lines or not any(lines[1] - lines[0] < len(hunk) and all(n in hunk for n in range(lines[0], lines[1] + 1))
                                for hunk in held.get(place["path"], [])):
            return False
    return True


def _off_hunks(case: dict, result: dict) -> bool:
    """Whether `apply` would refuse the Result whole as `finding_not_in_hunk`: a Finding it posts, as a review's comment
    or a check run's annotation, its lines given, on lines not all on one hunk of its file on the head's side of the
    case's diff, as the Task gives the diff to the model (decisions 0137, 0146 and NNNN). `apply`'s own readers read
    both, so the eval and a live Run refuse the same Result; a posted Finding with no lines `apply` refuses otherwise."""
    raised = {f["ref"]: f for f in result["findings"]}
    placed = [raised[ref] for _, _, ref in apply.posts(result.get("effects", {}))
              if ref in raised and _lines(raised[ref].get("location", {}))]
    shown = {"texts": [{"id": "diff:" + case["id"], "body": task.numbered(case["diff"])}]}
    posting = {"findings": placed, "effects": {"submit_review": [{"id": "e", "comments": [{"finding": f["ref"]} for f in placed]}]}}
    return apply.off_hunks(shown, posting) is not None


def _misses(expected: dict, raised: dict) -> list:
    """The codes of what a raised Finding has otherwise than the expected one."""
    return [code for ok, code in ((raised["category"] == expected["category"], MISSES[0]),
                                  (raised["severity"] == expected["severity"], MISSES[1]),
                                  (_at(expected, raised.get("location", {})), MISSES[2])) if not ok]


def _where_it_went(expected: dict, raised: list) -> list:
    """The codes of what became of an expected Finding that no Finding cited its criterion for: each fails the case alike,
    and tells a miss from a Finding that was raised and not cited. At a place the case gives, cited to no criterion, or
    to another, with what the nearest has otherwise; in a file of one of them but elsewhere; or in none of them."""
    there = [f for f in raised if _at(expected, f.get("location", {}))]
    if there:
        return ([WENT[2]] if any(f["criterion"] is None for f in there) else []) + \
               ([WENT[3]] if any(f["criterion"] is not None for f in there) else []) + \
               min((_misses(expected, f) for f in there), key=len)
    # A location whose lines cannot be read is nowhere, as `_overlaps` reads it.
    paths = {place["path"] for place in _places(expected)}
    in_file = any(f.get("location", {}).get("path") in paths and _lines(f["location"]) is not False for f in raised)
    return [WENT[1] if in_file else WENT[0]]


def _gates(raised: dict) -> bool:
    """Whether a raised Finding would hold a pull request, as `kernel/gate.py` reads a required Lens's: blocking or major,
    or a security Finding at any severity (decision 0144)."""
    return raised["severity"] in GATING_SEVERITIES or raised["category"] == SECURITY


def _criteria(role: str, root: pathlib.Path = ROOT):
    """The ids of the rubric a Role reviews by, or None where it has none this repo can read."""
    path = root / "config" / ("rubric-%s.json" % role)
    try:
        rubric = json.loads(path.read_text())
        return {c["id"] for c in rubric["criteria"]}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def off_rubric(case: dict, root: pathlib.Path = ROOT) -> bool:
    """Whether a case's expected Finding is of another severity or category than the rubric gives the criterion it asks
    about: a case that expects one would reward a Result `apply` refuses (decisions 0088 and 0095, issue 421). One that
    expects no Finding, or whose rubric lacks the criterion or cannot be read at all, is not: that is the scorer's
    `criterion_unknown`. A rubric read that `kernel/coverage.py` cannot read, as coverage refuses it wholesale, holds no
    case to it, so the case is off it: it fails closed, never asked of the model."""
    want = case["expected"]
    if want["finding"] is None:
        return False
    try:
        rubric = json.loads((root / "config" / ("rubric-%s.json" % case["role"])).read_text())
    except (OSError, ValueError):
        return False
    if not readable_rubric(rubric):
        return True
    given = {c["id"]: (c["severity_if_violated"], c["category"]) for c in rubric["criteria"]}
    return want["criterion"] in given and (want["finding"]["severity"], want["finding"]["category"]) != given[want["criterion"]]


def score(case: dict, result: dict, known: dict = None) -> dict:
    """{case, verdict, reasons}: `pass`, `fail` with the codes that say why, or `unreadable` when the case or the
    Result is not what its schema says, or the case's answer does not match its verdict; and `at_alternate`, true, on a
    pass whose Finding was at a place of `also_at` alone (decision 0143)."""
    known = schemas() if known is None else known
    try:
        wrong = validate(case, known["eval-case"], schemas=known) + validate(result, known["result"], schemas=known)
    except (SchemaError, KeyError):
        wrong = ["no schema"]
    if wrong:
        return {"case": case.get("id") if isinstance(case, dict) else None, "verdict": UNREADABLE, "reasons": ["schema"]}
    want = case["expected"]
    if (want["verdict"] == "finding") != (want["finding"] is not None):
        return {"case": case["id"], "verdict": UNREADABLE, "reasons": ["answer_disagrees_with_verdict"]}
    # Every place a case gives must be readable: its `location`, and each of `also_at` read inside a hunk of the case's
    # own diff on the head's side, which lines that cannot be read never are (decision 0143).
    if want["finding"] is not None and (_lines(want["finding"]["location"]) is False
                                        or not _in_hunks(want["finding"].get("also_at", []), case["diff"])):
        return {"case": case["id"], "verdict": UNREADABLE, "reasons": ["location_unreadable"]}
    # A case asks about one criterion of the rubric its Role reviews by; one the rubric lacks is nobody's to pass.
    criteria = _criteria(case["role"])
    if criteria is None or want["criterion"] not in criteria:
        return {"case": case["id"], "verdict": UNREADABLE, "reasons": ["criterion_unknown"]}
    if off_rubric(case):
        return {"case": case["id"], "verdict": UNREADABLE, "reasons": ["answer_off_rubric"]}
    # A completed Result `apply` would refuse whole for a posted Finding off every hunk posts nothing, so the case fails
    # by that alone, as the live Run would meet it (issue 574). One that did not complete `apply` refuses first as that.
    if result["status"] == "completed" and _off_hunks(case, result):
        return {"case": case["id"], "verdict": FAIL, "reasons": ["finding_not_in_hunk"]}
    reasons = []
    if result["status"] != "completed":
        reasons.append("result_not_completed")
    citing = [f for f in result["findings"] if f["criterion"] == want["criterion"]]
    covered = [c["verdict"] for c in result["coverage"] if c["criterion"] == want["criterion"]]
    if want["verdict"] == "finding":
        expected = want["finding"]
        if not citing:
            reasons += _where_it_went(expected, result["findings"])
        else:
            # One Finding must be the expected one in every respect; the nearest says what it missed.
            reasons += min((_misses(expected, f) for f in citing), key=len)
        if covered != ["finding"]:
            reasons.append("coverage_disagrees")
    else:
        # A clean case holds no fault a gate should stop, so a Finding that would hold it fails the case, whatever
        # criterion it cites or none, as one that cites the case's own criterion does at any severity (decision 0144).
        if citing or any(_gates(f) for f in result["findings"]):
            reasons.append("finding_raised_wrongly")
        if covered != ["met"]:
            reasons.append("criterion_not_met")
    said = {"case": case["id"], "verdict": PASS if not reasons else FAIL, "reasons": reasons}
    # A pass whose Finding was at an alternate place alone, never its `location`, is marked, so a report can count how
    # much of its score `also_at` gave (decision 0143).
    if said["verdict"] == PASS and want["verdict"] == "finding" and not any(
            not _misses(want["finding"], f) and _overlaps(want["finding"]["location"], f.get("location", {})) for f in citing):
        said["at_alternate"] = True
    return said


def main(argv: list = None, base: pathlib.Path = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print("usage: python3 -m tools.eval_result CASE RESULT", file=sys.stderr)
        return EXIT[UNREADABLE]
    # The scorer reads only what the job checked out beside it: each path is followed to where it really is, and one
    # outside the directory the scorer runs in is refused before it is opened; the refusal names no path.
    inside = os.path.realpath(str(pathlib.Path.cwd() if base is None else base))
    real = [os.path.realpath(os.path.join(inside, p)) for p in argv]
    if not all(path.startswith(inside + os.sep) for path in real):
        print(json.dumps({"case": None, "verdict": UNREADABLE, "reasons": ["file_outside"]}), file=sys.stderr)
        return EXIT[UNREADABLE]
    try:
        with open(real[0], encoding="utf-8") as first, open(real[1], encoding="utf-8") as second:
            case, result = json.load(first), json.load(second)
    except (OSError, ValueError):
        print(json.dumps({"case": None, "verdict": UNREADABLE, "reasons": ["file"]}), file=sys.stderr)
        return EXIT[UNREADABLE]
    said = score(case, result)
    print(json.dumps(said))
    return EXIT[said["verdict"]]


if __name__ == "__main__":
    sys.exit(main())
