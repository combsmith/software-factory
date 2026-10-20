"""Score one Result against one held-out case: did the review raise the Finding the case expects, or cover the criterion
as met? `python3 -m tools.eval_result CASE RESULT` prints the score and exits 0 on a pass, 1 on a fail and 2 when either
file cannot be read. The case comes from the private home at run time; nothing here reads it from this repo."""
from __future__ import annotations

import json
import pathlib
import sys

from tools.jsonschema_lite import SchemaError, validate

ROOT = pathlib.Path(__file__).resolve().parent.parent
PASS, FAIL, UNREADABLE = "pass", "fail", "unreadable"
EXIT = {PASS: 0, FAIL: 1, UNREADABLE: 2}


def schemas(root: pathlib.Path = ROOT) -> dict:
    return {p.name[: -len(".schema.json")]: json.loads(p.read_text()) for p in sorted((root / "schemas").glob("*.schema.json"))}


def _overlaps(expected: dict, raised: dict) -> bool:
    """Whether a raised Finding's location is the expected one: the same path, and its lines, where both give them,
    overlapping; a location given without lines is the whole file."""
    if raised.get("path") != expected["path"]:
        return False
    if "start_line" not in expected or "start_line" not in raised:
        return True
    e_start, e_end = expected["start_line"], expected.get("end_line", expected["start_line"])
    r_start, r_end = raised["start_line"], raised.get("end_line", raised["start_line"])
    return r_start <= e_end and e_start <= r_end


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
    reasons = []
    if result["status"] != "completed":
        reasons.append("result_not_completed")
    citing = [f for f in result["findings"] if f["criterion"] == want["criterion"]]
    covered = [c["verdict"] for c in result["coverage"] if c["criterion"] == want["criterion"]]
    if want["verdict"] == "finding":
        if not citing:
            reasons.append("finding_not_raised")
        else:
            expected = want["finding"]
            if not any(f["category"] == expected["category"] for f in citing):
                reasons.append("category_differs")
            if not any(f["severity"] == expected["severity"] for f in citing):
                reasons.append("severity_differs")
            if not any(_overlaps(expected["location"], f.get("location", {})) for f in citing):
                reasons.append("location_differs")
        if covered != ["finding"]:
            reasons.append("coverage_disagrees")
    else:
        if citing:
            reasons.append("finding_raised_wrongly")
        if covered != ["met"]:
            reasons.append("criterion_not_met")
    return {"case": case["id"], "verdict": PASS if not reasons else FAIL, "reasons": reasons}


def main(argv: list = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print("usage: python3 -m tools.eval_result CASE RESULT", file=sys.stderr)
        return EXIT[UNREADABLE]
    try:
        case, result = (json.loads(pathlib.Path(p).read_text()) for p in argv)
    except (OSError, ValueError) as err:
        print(json.dumps({"case": None, "verdict": UNREADABLE, "reasons": ["file"]}), file=sys.stderr)
        return EXIT[UNREADABLE]
    said = score(case, result)
    print(json.dumps(said))
    return EXIT[said["verdict"]]


if __name__ == "__main__":
    sys.exit(main())
