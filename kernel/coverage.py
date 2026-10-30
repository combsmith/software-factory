"""Coverage: whether a reviewing Result reports on every criterion of its rubric that applies (design §3.14, I-37).

The Kernel never reads a Result (§3.9). `apply` asks `covered` before any Effect: a Run whose Result is uncovered ends
failed, its outcome `item`, and one whose rubric or paths cannot be read ends failed, its outcome `environment`
(decision 0029). What the Kernel reads is that run record.
"""
from __future__ import annotations

from kernel import terms as t
from kernel.derive import matches, names, readable_file, readable_pattern


def is_criterion_id(value) -> bool:
    """Whether `value` is a criterion's id in its one form: capital letters, a hyphen, then digits."""
    if not isinstance(value, str):
        return False
    letters, hyphen, digits = value.partition(t.HYPHEN)
    return (hyphen != "" and letters != "" and digits != "" and all(c in t.CAPITALS for c in letters)
            and all(c in t.DIGITS for c in digits))


def is_code(value) -> bool:
    """Whether `value` is a code: lower-case letters and underscores, at least one, and never a sentence."""
    return isinstance(value, str) and value != "" and all(c in t.CODE_CHARS for c in value)


def readable_rubric(rubric) -> bool:
    """Whether a rubric's criteria can be read: at least one, each an object with an id in its form, given once, and
    the severity and the category a Finding that cites it has (design section 3.14, issue 407)."""
    criteria = rubric.get("criteria") if isinstance(rubric, dict) else None
    if not (isinstance(criteria, list) and criteria and all(isinstance(c, dict) for c in criteria)):
        return False
    ids = [c.get("id") for c in criteria]
    return (all(is_criterion_id(i) for i in ids) and len(set(ids)) == len(ids)
            and all(c.get("severity_if_violated") in t.SEVERITIES for c in criteria)
            and all(c.get("category") in t.CATEGORIES for c in criteria))


def readable_changes(changed) -> bool:
    """Whether the files the pull request changes can be read: each read whole (readable_file). A list that was not
    read in full is given as None, and cannot be."""
    return isinstance(changed, list) and all(readable_file(entry) for entry in changed)


def applies(criterion: dict, paths: list) -> bool:
    """Whether `criterion` applies to a change of `paths`: it has no `applies_when`, or one of the paths is what one of
    its patterns names (matches, the one matcher). One whose `applies_when` cannot be read applies: read as applying to
    nothing, it would let a Result leave it out."""
    if "applies_when" not in criterion:
        return True
    when = criterion["applies_when"]
    patterns = when.get("paths") if isinstance(when, dict) else None
    if not (isinstance(patterns, list) and patterns and all(readable_pattern(p) for p in patterns)):
        return True
    return any(matches(p, path) for p in patterns for path in paths)


def reported(entry: dict, cited: bool) -> bool:
    """Whether one entry reports on its criterion, which a Finding of the Result cites or not: `met`, `finding` where a
    Finding cites it, or `not_applicable` with a reason that is a code. A Finding that cites a criterion whose verdict
    is not `finding` contradicts it."""
    verdict = entry.get("verdict")
    if verdict not in t.VERDICTS:
        return False
    if verdict == t.FINDING and not cited:
        return False
    if cited and verdict != t.FINDING:
        return False
    return verdict != t.NOT_APPLICABLE or is_code(entry.get("reason"))


def _off(said, out: list) -> None:
    """Name `said`, an id the rubric does not have, among the criteria `out` holds uncovered: as that id, or as
    `unreadable` when it is none, once."""
    shown = said if is_criterion_id(said) else "unreadable"
    if shown not in out:
        out.append(shown)


def covered(rubric, coverage, findings, changed) -> tuple:
    """Whether a reviewing Result reports on every criterion of `rubric` that applies to the change, as
    ("covered", []), ("uncovered", ids) or ("unreadable", []).

    `coverage` is what the Result says of each criterion, `findings` its Findings, and `changed` the files the pull
    request changes, as the facts give them. A criterion applies when it has no `applies_when`, or when a path the
    change touches, a renamed file's previous path among them (names), is what one of its patterns names. One that
    applies is uncovered when it has no entry, or two; when its entry does not report on it (reported); and so is an
    entry for an id the rubric does not have, shown as that id, or as `unreadable` when it is none. An entry for a
    criterion that does not apply is passed over. A Finding that cites a criterion of the rubric has the severity the
    rubric gives it, never the model's: one at another severity leaves that criterion uncovered, whether it applies or
    not, so its severity cannot move it off the gate (issue 373). So does one of another category than the rubric
    gives it, so its category cannot move it from the guards it is held to, and it is never rewritten from the rubric
    (issue 407). A Finding that cites an id the rubric does not have
    is uncovered as a coverage entry for one is, shown as that id, or as `unreadable` when it is none; one that cites
    none keeps the model's severity and category. A rubric, or paths, that cannot be read
    are unreadable, never covered: the Factory's fault, not the item's.
    """
    if not (readable_rubric(rubric) and readable_changes(changed)):
        return "unreadable", []
    paths = names(changed)
    ids = [c["id"] for c in rubric["criteria"]]
    applying = [c["id"] for c in rubric["criteria"] if applies(c, paths)]
    if not (isinstance(coverage, list) and isinstance(findings, list)):
        return "uncovered", applying
    cites = [f.get("criterion") for f in findings if isinstance(f, dict)]
    out = []
    for c in applying:
        mine = [e for e in coverage if isinstance(e, dict) and e.get("criterion") == c]
        if len(mine) != 1 or not reported(mine[0], c in cites):
            out.append(c)
    given = {c["id"]: (c["severity_if_violated"], c["category"]) for c in rubric["criteria"]}
    for f in findings:
        said = f.get("criterion") if isinstance(f, dict) else None
        if said in ids and (f.get("severity"), f.get("category")) != given[said] and said not in out:
            out.append(said)
        elif said is not None and said not in ids:
            _off(said, out)
    for e in coverage:
        said = e.get("criterion") if isinstance(e, dict) else None
        if said not in ids:
            _off(said, out)
    return ("uncovered", out) if out else ("covered", [])
