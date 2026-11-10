"""What a review may ask of the model more than once, and how the answers become one Result (issue 581).

`settings(config)` reads the Harness's optional `review` block: a pass per changed file, more than one run over the
whole Task, a fault checklist per criterion, reading the head before a criterion is met. The committed configuration
gives none of them, so a live Run and the gate are asked as they always were; a private replay sets one in its own copy
to measure one approach against the same commit. `split(task)` gives one Task per changed file, and `union(results)`
joins the Results by the merge rule the record states.
"""
from __future__ import annotations

import copy
import re

from harness import task as tasks

# What a review is asked when the configuration says nothing of it: one pass over the whole Task, once, and no more told
# than the Role's instructions and its rubric. Each key a configuration may set is here, and no other is read.
DEFAULTS = {"passes": "whole", "runs": 1, "checklist": False, "read_head": False}
# A change of more files than this is judged in one pass, so a replay's cost per case has a bound.
MOST_FILES = 8
# The head's path of one file's part of a diff, from git's header line.
HEADER = re.compile(r"diff --git a/\S+ b/(\S+)")
# What a pass of one changed file is told after its instructions, so that it judges that file alone and is not left to
# read the rest as missing (the Claude review of issue 581).
ONE_FILE = ("\n\nThis pass judges one changed file of the pull request, %s, alone: the diff in the Task holds its part "
            "only. The other changed files, %s, are judged in passes of their own, so do not answer incomplete for them, "
            "and judge each criterion on this file's part alone, not applicable where it touches only the others.")
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
    if "review" not in config:
        return dict(DEFAULTS)
    given = config["review"]
    if not isinstance(given, dict) or set(given) - set(ALLOWED) or not all(ALLOWED[k](v) for k, v in given.items()):
        raise ValueError("the configuration's review block is not as harness/1 allows")
    # A replay measures one approach against the same commit: two switched on at once would measure neither, and multiply
    # the calls a case may make.
    if len([k for k, v in given.items() if v != DEFAULTS[k]]) > 1:
        raise ValueError("the configuration's review block switches on more than one approach")
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
    # A part whose path git's header does not give plainly, as a quoted name with a tab in it, leaves the Task whole: each
    # pass is told its own path and the others'.
    if not 2 <= len(parts) <= MOST_FILES or not all(part.startswith("diff --git ") and HEADER.match(part) for part in parts):
        return [the_task]
    out = []
    for part in parts:
        one = copy.deepcopy(the_task)
        one["texts"][at[0]] = dict(one["texts"][at[0]], body=part)
        out.append(one)
    return out


def path(part: dict) -> str:
    """The path a Task of one changed file judges, as its diff's header names it at the head; none where it names none."""
    body = [t for t in part["texts"] if t["id"].startswith("diff:")][0]["body"]
    found = HEADER.match(body)
    return found.group(1) if found else None


def asked(the_task: dict, review: dict) -> list:
    """`(task, note)` for each call a review makes under `review`: each changed file's Task with the note that tells it
    the rest are judged in other passes, or the whole Task with none, each `runs` times."""
    parts = split(the_task) if review["passes"] == "per_file" else [the_task]
    named = [path(part) for part in parts] if len(parts) > 1 else []
    notes = [ONE_FILE % (named[i], ", ".join(n for j, n in enumerate(named) if j != i)) for i in range(len(named))] or [""]
    return [(part, note) for part, note in zip(parts, notes) for _ in range(review["runs"])]


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


def _covered(results: list, cited: set) -> list:
    """Each criterion any Result covers, in the order first given: `finding` where a kept Finding cites it, `cited`, so
    that the joined Result is covered as `apply` reads it (`kernel.coverage.covered`); otherwise, of the words that are not
    `finding`, `met` where at least one judged it met and each other met or not applicable, `met` too where none is left,
    every Finding that cited it merged into one kept at its place under another criterion; otherwise as the first that
    covers it with such a word says."""
    order, said = [], {}
    for result in results:
        for entry in result["coverage"]:
            if entry["criterion"] not in said:
                order.append(entry["criterion"])
                said[entry["criterion"]] = []
            said[entry["criterion"]].append(entry)
    out = []
    for criterion in order:
        rest = [e for e in said[criterion] if e["verdict"] != "finding"]
        verdicts = [e["verdict"] for e in rest]
        if criterion in cited:
            out.append({"criterion": criterion, "verdict": "finding", "reason": None})
        elif not rest or ("met" in verdicts and set(verdicts) <= {"met", "not_applicable"}):
            out.append({"criterion": criterion, "verdict": "met", "reason": None})
        else:
            out.append(dict(rest[0]))
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
    raised, answer = [], []
    for n, result in enumerate(results):
        posted = {item["finding"]: (kind, item["body"]) for kind, field in POSTED
                  for effect in result["effects"].get(kind, []) for item in effect[field]}
        raised += [(finding, posted.get(finding["ref"])) for finding in result["findings"]]
        answer += [n] * len(result["findings"])
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
        # Agreement is counted by answer, not by Finding: one answer raising three at a place is one voice.
        voices = {triple: len({answer[i] for i, t in zip(group, said) if t == triple}) for triple in said}
        most = max(said, key=lambda triple: (voices[triple], -said.index(triple)))
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
        # A kind is posted only where a kept Finding is posted by it, never from the answer of a Finding merged away; where
        # no Finding is kept at all, as the first answer posted it.
        if not items[kind] and (findings or kind not in results[0]["effects"]):
            continue
        if not findings:
            for effect in results[0]["effects"][kind]:
                ids += 1
                effects.setdefault(kind, []).append(dict(effect, id="e%d" % ids))
            continue
        ids += 1
        # A submitted review keeps the first body any answer gave it; a check run has none.
        body = {"body": next((e["body"] for e in given if e["body"] is not None), None)} if kind == "submit_review" else {}
        effects[kind] = [dict({"id": "e%d" % ids, field: items[kind]}, **body)]
    cited = {f["criterion"] for f in findings if f.get("criterion")}
    return dict(results[0], findings=findings, effects=effects, coverage=_covered(results, cited), usage=usage)
