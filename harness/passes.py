"""What a review may ask of the model more than once, and how the answers become one Result (issue 581).

`settings(config)` reads the Harness's optional `review` block: a pass per changed file, more than one run over the
whole Task, a fault checklist per criterion, reading the head before a criterion is met. The committed configuration
gives none of them, so a live Run and the gate are asked as they always were; a private replay sets one in its own copy
to measure one approach against the same commit. `split(task)` gives one Task per changed file, and `union(results)`
joins the Results by the merge rule the record states.
"""
from __future__ import annotations

import copy

from harness import task as tasks

# What a review is asked when the configuration says nothing of it: one pass over the whole Task, once, and no more told
# than the Role's instructions and its rubric. Each key a configuration may set is here, and no other is read.
DEFAULTS = {"passes": "whole", "runs": 1, "checklist": False, "read_head": False}
# A change of more files than this is judged in one pass, so a replay's cost per case has a bound.
MOST_FILES = 8
# Where each raised Finding is posted, by the Effect's type and the list in it that names Findings (effect/1).
POSTED = (("submit_review", "comments"), ("create_check_run", "annotations"))
# The counts a Result's `usage` sums over its calls; every other field is the first call's.
SUMMED = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens", "turns", "cost_usd",
          "seconds")


# What each key may be, as harness/1 gives it, so that a private copy edited by hand is refused, never misread.
ALLOWED = {"passes": lambda v: v in ("whole", "per_file"), "runs": lambda v: type(v) is int and 1 <= v <= 3,
           "checklist": lambda v: v is True or v is False, "read_head": lambda v: v is True or v is False}


def settings(config: dict) -> dict:
    """The review's settings, as the Harness's configuration gives them over DEFAULTS; DEFAULTS where it gives no block.
    A block with a key or a value harness/1 does not allow is a ValueError: a replay is never measured on a misread one."""
    given = config.get("review")
    if given is None:
        return dict(DEFAULTS)
    if not isinstance(given, dict) or set(given) - set(ALLOWED) or not all(ALLOWED[k](v) for k, v in given.items()):
        raise ValueError("the configuration's review block is not as harness/1 allows")
    return dict(DEFAULTS, **given)


def split(the_task: dict) -> list:
    """One Task for each changed file: the Task whole but for its diff, which holds that file's part alone, so that a
    fault in a file read late is not crowded out. The head stays whole for each. A Task of one file, of more than
    MOST_FILES, or whose diff cannot be cut at each file's header, is asked as it is."""
    at = [i for i, text in enumerate(the_task["texts"]) if text["id"].startswith("diff:")]
    if len(at) != 1:
        return [the_task]
    parts = tasks.FILE_START.split(the_task["texts"][at[0]]["body"])
    parts = [part for part in parts if part]
    if not 2 <= len(parts) <= MOST_FILES or not all(part.startswith("diff --git ") for part in parts):
        return [the_task]
    out = []
    for part in parts:
        one = copy.deepcopy(the_task)
        one["texts"][at[0]] = dict(one["texts"][at[0]], body=part)
        out.append(one)
    return out


def _lines(finding: dict):
    """`(path, first, last)` of a Finding's place, or None where it names no lines: such a Finding is at no place."""
    where = finding.get("location") or {}
    if "start_line" not in where:
        return None
    return where["path"], where["start_line"], where.get("end_line", where["start_line"])


def _overlap(one, other) -> bool:
    return one is not None and other is not None and one[0] == other[0] and one[1] <= other[2] and other[1] <= one[2]


def _usage(results: list) -> dict:
    """The first call's `usage`, each count summed over every call, or none where any call counted none."""
    usage = dict(results[0]["usage"])
    for name in SUMMED:
        said = [r["usage"].get(name) for r in results]
        usage[name] = sum(said) if all(isinstance(n, (int, float)) and not isinstance(n, bool) for n in said) else None
    return usage


def _covered(results: list) -> list:
    """Each criterion any Result covers, in the order first given: `finding` where any raised one; `met` where at least
    one judged it met and each other met or not applicable; otherwise as the first that covers it says."""
    order, said = [], {}
    for result in results:
        for entry in result["coverage"]:
            if entry["criterion"] not in said:
                order.append(entry["criterion"])
                said[entry["criterion"]] = []
            said[entry["criterion"]].append(entry)
    out = []
    for criterion in order:
        verdicts = [e["verdict"] for e in said[criterion]]
        if "finding" in verdicts:
            out.append({"criterion": criterion, "verdict": "finding", "reason": None})
        elif "met" in verdicts and set(verdicts) <= {"met", "not_applicable"}:
            out.append({"criterion": criterion, "verdict": "met", "reason": None})
        else:
            out.append(dict(said[criterion][0]))
    return out


def union(results: list) -> dict:
    """One Result of several of one Task: the first that did not complete, by its own reason, where any did not;
    otherwise each Finding of every Result, those at one place one Finding, the one most of them agree on by criterion,
    severity and category, the earliest on a tie, each posted as its own Result posted it; coverage by `_covered`; and
    `usage` summed. A single Result is itself."""
    if len(results) == 1:
        return results[0]
    usage = _usage(results)
    for result in results:
        if result["status"] != "completed":
            return dict(result, usage=usage)
    raised = []
    for result in results:
        posted = {item["finding"]: (kind, item["body"]) for kind, field in POSTED
                  for effect in result["effects"].get(kind, []) for item in effect[field]}
        raised += [(finding, posted.get(finding["ref"])) for finding in result["findings"]]
    # Findings at one place, the same path with lines that overlap, are one, whatever each cites: decision 0160 fails a
    # case with two at its place, so a union that kept both would score a fault found twice as worse than found once.
    # Each group holds the places of its Findings in `raised`, in order.
    groups = []
    for at, (finding, _) in enumerate(raised):
        joined = [g for g in groups if any(_overlap(_lines(finding), _lines(raised[i][0])) for i in g)]
        groups = [g for g in groups if g not in joined] + [sorted([at] + [i for g in joined for i in g])]
    kept = []
    for group in sorted(groups):
        said = [(raised[i][0].get("criterion"), raised[i][0]["severity"], raised[i][0]["category"]) for i in group]
        most = max(said, key=lambda triple: (said.count(triple), -said.index(triple)))
        kept.append(raised[group[said.index(most)]])
    findings, items = [], {kind: [] for kind, _ in POSTED}
    for n, (finding, post) in enumerate(kept, 1):
        ref = "n%d" % n
        findings.append(dict(finding, ref=ref))
        if post is not None:
            items[post[0]].append({"finding": ref, "body": post[1]})
    # An Effect of any other type is the first Result's, as it asked it.
    effects, ids = {}, 0
    for kind, given in results[0]["effects"].items():
        if kind in dict(POSTED):
            continue
        effects[kind] = []
        for effect in given:
            ids += 1
            effects[kind].append(dict(effect, id="e%d" % ids))
    for kind, field in POSTED:
        given = [effect for result in results for effect in result["effects"].get(kind, [])]
        if not given:
            continue
        ids += 1
        # A submitted review keeps the first body any answer gave it; a check run has none.
        body = {"body": next((e["body"] for e in given if e["body"] is not None), None)} if kind == "submit_review" else {}
        effects[kind] = [dict({"id": "e%d" % ids, field: items[kind]}, **body)]
    return dict(results[0], findings=findings, effects=effects, coverage=_covered(results), usage=usage)
