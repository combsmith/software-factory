"""Score one Result against one held-out case: did the review raise the Finding the case expects, or cover the criterion
as met? `python3 -m tools.eval_result CASE RESULT` prints the score and exits 0 on a pass, 1 on a fail and 2 when either
file cannot be read. The case comes from the private home at run time; nothing here reads it from this repo."""
from __future__ import annotations

import json
import os
import pathlib
import sys

from kernel.coverage import readable_rubric
from tools.jsonschema_lite import SchemaError, validate

ROOT = pathlib.Path(__file__).resolve().parent.parent
PASS, FAIL, UNREADABLE = "pass", "fail", "unreadable"
EXIT = {PASS: 0, FAIL: 1, UNREADABLE: 2}


def schemas(root: pathlib.Path = ROOT) -> dict:
    return {p.name[: -len(".schema.json")]: json.loads(p.read_text()) for p in sorted((root / "schemas").glob("*.schema.json"))}


MISSES = ("category_differs", "severity_differs", "location_differs")


def _lines(location: dict):
    """(first, last) of a location's lines; None where it names none, the whole file; False where they cannot be read:
    an end with no start, or an end before the start."""
    if "start_line" not in location:
        return False if "end_line" in location else None
    first, last = location["start_line"], location.get("end_line", location["start_line"])
    return (first, last) if first <= last else False


def _overlaps(expected: dict, raised: dict) -> bool:
    """Whether a raised Finding's location is the expected one: the same path, and its lines, where both give them,
    overlapping; a location given without lines is the whole file, and one whose lines cannot be read is nowhere."""
    if raised.get("path") != expected["path"]:
        return False
    theirs, ours = _lines(raised), _lines(expected)
    if theirs is False:
        return False
    if theirs is None or ours is None:
        return True
    return theirs[0] <= ours[1] and ours[0] <= theirs[1]


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
    Result is not what its schema says, or the case's answer does not match its verdict."""
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
    if want["finding"] is not None and _lines(want["finding"]["location"]) is False:
        return {"case": case["id"], "verdict": UNREADABLE, "reasons": ["location_unreadable"]}
    # A case asks about one criterion of the rubric its Role reviews by; one the rubric lacks is nobody's to pass.
    criteria = _criteria(case["role"])
    if criteria is None or want["criterion"] not in criteria:
        return {"case": case["id"], "verdict": UNREADABLE, "reasons": ["criterion_unknown"]}
    if off_rubric(case):
        return {"case": case["id"], "verdict": UNREADABLE, "reasons": ["answer_off_rubric"]}
    reasons = []
    if result["status"] != "completed":
        reasons.append("result_not_completed")
    citing = [f for f in result["findings"] if f["criterion"] == want["criterion"]]
    covered = [c["verdict"] for c in result["coverage"] if c["criterion"] == want["criterion"]]
    if want["verdict"] == "finding":
        if not citing:
            reasons.append("finding_not_raised")
        else:
            # One Finding must be the expected one in every respect; the nearest says what it missed.
            expected = want["finding"]
            misses = [[code for ok, code in ((f["category"] == expected["category"], MISSES[0]),
                                             (f["severity"] == expected["severity"], MISSES[1]),
                                             (_overlaps(expected["location"], f.get("location", {})), MISSES[2]))
                       if not ok] for f in citing]
            reasons += min(misses, key=len)
        if covered != ["finding"]:
            reasons.append("coverage_disagrees")
    else:
        if citing:
            reasons.append("finding_raised_wrongly")
        if covered != ["met"]:
            reasons.append("criterion_not_met")
    return {"case": case["id"], "verdict": PASS if not reasons else FAIL, "reasons": reasons}


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
