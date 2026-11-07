"""The `run` job: one Task, one call of the Engine, one Result (design sections 2.3 and 3.10, issue 194).

    python3 -m harness.run RECORD RUN FACTS DIFF TEXTS ROLE FINDINGS OUT [HEAD]
    python3 -m harness.run TASK OUT

The second form is the workflow's: TASK is the folder `python3 -m harness.read` wrote, holding each of the first
form's files by its name, the Run id among them in `run`, and the head it unpacked, `head/`, which a review reads as
the folder the CLI starts in (decision 0138); a review given no head is never asked.

RECORD is the pass record the Run was admitted in, RUN its Run id, FACTS the item's facts as the Run reads them, DIFF the
bytes of the pull request's diff as GitHub served them, empty for an issue, TEXTS
the texts read for it, each with who wrote it, ROLE the Role's manifest, FINDINGS the Finding ids the Task names, as
JSON files, and OUT a directory that does not exist yet. The job writes OUT/result.json and OUT/result.sha256, and
nothing else of the model: the log carries the digest alone, never a field of the Result, since nothing is handed from
job to job through the log (section 3.10). The CLI is the one at the path the job's environment names, CLAUDE_CLI, and
the credential the one under CLAUDE_CODE_OAUTH_TOKEN. A Run whose Task cannot be built writes no Result and fails.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time
import uuid

from harness import engine, shared, steps, task
from kernel.coverage import readable_rubric

ROOT = pathlib.Path(__file__).resolve().parent.parent
CLI = "CLAUDE_CLI"


def configuration(root: pathlib.Path = ROOT) -> dict:
    """What the Task and the Engine are told beside the pass record: the Maintainer, the names the Factory's Roles act
    under, config/harness.json, and the longest diff a Task carries, the Kernel's own limit, so the bound the Kernel
    holds a pull request to and the one a Task is cut at are one (issue 327). The Release is the pass record's: one
    Release, one path (decision 0006)."""
    hooks = json.loads((root / "config" / "hooks.json").read_text())
    apps = json.loads((root / "config" / "apps.json").read_text())
    defaults = json.loads((root / "config" / "defaults.json").read_text())
    roles = sorted({app["name"] + "[bot]" for app in apps["apps"].values()} | set(defaults["required_lenses"]["model"]))
    return {"maintainer": hooks["maintainer"]["login"], "roles": roles, "approver": defaults["approver"],
            "harness": json.loads((root / "config" / "harness.json").read_text()),
            # The one bound on the change a Task carries, the Kernel's own (issue 327).
            "max_diff_characters": defaults["limits"]["max_diff_characters"]}


# The Intents whose Result covers a rubric (design section 3.14, decision 0049): a Run of one is never asked without it.
REVIEWING = ("review-change",)


class RubricUnreadable(task.Refused):
    """A reviewing Intent's rubric is missing, names another Role or Intent, or cannot be read."""


def instructions(root: pathlib.Path, the_task: dict) -> str:
    """What the model is told before the Task, from the Release's own files by the admitted Role's name and never from
    the item: the Role's instructions, `roles/<role>/prompt.md`, and the rubric its Intent's Result covers,
    `config/rubric-<role>.json`, where one names this Intent (decision 0059). Both are a model Lens's inputs (decision
    0052). A Role with no instructions in the Release has no Task, and a reviewing Intent whose rubric is missing, names
    another Role or Intent, or cannot be read is RubricUnreadable, before anything is asked."""
    prompt = root / "roles" / the_task["role"] / "prompt.md"
    if not prompt.is_file():
        raise task.Refused("the Role has no instructions in the Release")
    told = engine.ROLE + prompt.read_text(encoding="utf-8")
    rubric = root / "config" / ("rubric-%s.json" % the_task["role"])
    try:
        held = json.loads(rubric.read_text(encoding="utf-8")) if rubric.is_file() else None
    except (OSError, ValueError):
        held = None
    if (isinstance(held, dict) and (held.get("role"), held.get("intent")) == (the_task["role"], the_task["intent"])
            and readable_rubric(held)):
        told += engine.RUBRIC + json.dumps(held, sort_keys=True)
    elif the_task["intent"] in REVIEWING:
        raise RubricUnreadable("rubric_unreadable")
    return told


def cli_call(args: list, env: dict, timeout: float, head: str = None):
    """The CLI, started in an empty directory of its own, or in the head it reviews where one is given (decision 0138),
    with nothing on its input and its answer captured."""
    with tempfile.TemporaryDirectory() as empty:
        return subprocess.run(args, env=env, timeout=timeout, cwd=empty if head is None else head,
                              stdin=subprocess.DEVNULL, capture_output=True, text=True, errors="replace", check=False)


def job(paths: list, job_env: dict, config: dict, call=None, clock=time.monotonic, session=None, base=None) -> str:
    """Build the Task, run the Engine, and write the Result and its digest into OUT. Returns the digest.

    The job reads and writes only inside the directory it runs in, `base`, by default the working directory: each path
    is followed to where it really is, and one outside is refused before anything is opened, naming no path. A ninth
    path, the workflow's form's, is the head the reader unpacked, which a review reads (decision 0138)."""
    inside = os.path.realpath(str(pathlib.Path.cwd() if base is None else base))
    record, run, facts, diff, texts, role, findings, out = paths[:8]
    head = os.path.realpath(os.path.join(inside, paths[8])) if len(paths) > 8 else None
    if head is not None and not head.startswith(inside + os.sep):
        raise task.Refused("a path the job was given is outside the directory it runs in")
    # OUT is new, and not a link either: a link to nowhere would be followed and the Result written where it points.
    if os.path.lexists(os.path.join(inside, out)):
        raise task.Refused("OUT exists; the Result is written into a new directory")
    real = [os.path.realpath(os.path.join(inside, p)) for p in (record, facts, diff, texts, role, findings, out)]
    if not all(path.startswith(inside + os.sep) for path in real):
        raise task.Refused("a path the job was given is outside the directory it runs in")
    record, facts, diff, texts, role, findings, out = real

    def read(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    admitted = read(record)
    if not isinstance(admitted, dict) or not isinstance(admitted.get("release"), str):
        raise task.Refused("the pass record is no pass/1")
    config = dict(config, release=admitted["release"])
    with open(diff, "rb") as f:
        change = f.read()
    the_task = task.build(admitted, run, read(facts), read(texts), read(role), read(findings), config, change)
    result = answer(the_task, job_env, config, call, clock, session or str(uuid.uuid4()), head)
    data = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    digest = "sha256:" + hashlib.sha256(data).hexdigest()
    # The Result is its own user's alone to read, as every step's files are (`harness/steps.py`).
    os.makedirs(out, 0o700)
    steps.write(out, "result.json", data)
    steps.write(out, "result.sha256", (digest + "\n").encode())
    return digest


def answer(the_task: dict, job_env: dict, config: dict, call=None, clock=time.monotonic, session: str = None,
           head: str = None) -> dict:
    """The Result of `the_task`: the Engine's, or a failed one for the Factory's own fault read before the CLI starts.
    A live Run and a held-out case are answered by this one function (issue 309, ruling 5). A reviewing Intent reads the
    pull request's head, the folder `head`, with the read tools alone; one with no head to read is never asked, by the
    Factory's fault `head_unreadable` (decision 0138). `call` is the CLI's, given the head as its folder."""
    session = session or str(uuid.uuid4())
    fault, told = None, None
    reviewing = the_task["intent"] in REVIEWING
    if reviewing and any(o["kind"] == "diff" for o in the_task["omitted"]):
        # The Kernel holds a pull request whose diff no Task carries whole; one admitted all the same is never reviewed
        # in part (issue 327).
        fault = "diff_not_whole"
    elif reviewing and not (isinstance(head, str) and os.path.isdir(head)):
        fault = "head_unreadable"
    else:
        try:
            told = instructions(ROOT, the_task)
        except RubricUnreadable:
            fault = "rubric_unreadable"
    if fault:
        # The Factory's fault, read before the CLI is started: a failed Result, and no model call spent (issue 330).
        return engine.failed(the_task, fault, engine.usage_of(the_task, config["harness"], session))
    asked = call or cli_call

    def called(args, env, timeout):
        # The head is the folder the CLI starts in, for a review alone; any other Intent's call is as it always was.
        return asked(args, env=env, timeout=timeout, head=head) if reviewing else asked(args, env=env, timeout=timeout)
    focus = passes(the_task)
    if not focus:
        return engine.run(the_task, job_env.get(CLI, ""), job_env, config["harness"], called, clock, session, told,
                          read=reviewing)
    # Issue 581's prototype: one Run of the Engine for each changed file, each reading the whole diff and the head, and
    # raising the Findings that sit on its own file's changed lines; their Results joined into one.
    results = []
    for at, path in enumerate(focus):
        one = dict(the_task, focus={"path": path})
        result = engine.run(one, job_env.get(CLI, ""), job_env, config["harness"], called, clock,
                            session if at == 0 else str(uuid.uuid4()), told, read=True)
        results.append(result)
        if result["status"] != "completed":
            break
    return joined(the_task, results)


# The most changed files a review is asked one Run each for; a change of more is reviewed whole, in one Run.
MOST_PASSES = 6
PATH = re.compile(r"[^\s\x00-\x1f\x7f]+")


def passes(the_task: dict) -> list:
    """The paths of a review's changed files, in the diff's order, one Run each, or [] where it is asked one Run: an
    Intent that does not review, a change of one file or of more than MOST_PASSES, or a path no Task's focus can hold."""
    if the_task["intent"] not in REVIEWING or not the_task["texts"] or not the_task["texts"][0]["id"].startswith("diff:"):
        return []
    paths = []
    for part in task.FILE_START.split(the_task["texts"][0]["body"]):
        head = re.search(r"^\+\+\+ b/(.+)$", part, re.M)
        base = re.search(r"^--- a/(.+)$", part, re.M)
        path = (head or base).group(1) if (head or base) else None
        if path is None and part.startswith("diff --git "):
            return []
        if path is not None and path not in paths:
            paths.append(path)
    if not 1 < len(paths) <= MOST_PASSES or not all(PATH.fullmatch(p) for p in paths):
        return []
    return paths


def _same(one: dict, other: dict) -> bool:
    """Whether two Findings are one: the same criterion, or none and the same category, in the same file, on lines that
    overlap, or neither with lines."""
    if (one["criterion"], one["criterion"] or one["category"]) != (other["criterion"], other["criterion"] or other["category"]):
        return False
    here, there = one.get("location", {}), other.get("location", {})
    if here.get("path") != there.get("path"):
        return False
    if "start_line" not in here or "start_line" not in there:
        return "start_line" not in here and "start_line" not in there
    return (here["start_line"] <= there.get("end_line", there["start_line"])
            and there["start_line"] <= here.get("end_line", here["start_line"]))


def joined(the_task: dict, results: list) -> dict:
    """One Result of a review's Runs, one for each changed file: the first that did not complete, whole, with the usage
    of all; or every Finding once, numbered afresh, each posted as its own Run asked, the Dispositions once each, and a
    criterion `finding` where a Finding cites it, else `met` where any Run met it, else as the first Run judged it. One
    that does not hold to result/1 is `failed`, `result_invalid`."""
    usage = dict(results[0]["usage"])
    for name in engine.COUNTS + ("turns",):
        values = [r["usage"][name] for r in results]
        usage[name] = sum(values) if all(type(v) is int for v in values) else None
    costs = [r["usage"]["cost_usd"] for r in results]
    usage["cost_usd"] = sum(costs) if all(isinstance(c, (int, float)) for c in costs) else None
    usage["seconds"] = round(sum(r["usage"]["seconds"] for r in results), 3)
    models = {r["usage"]["answering_model"] for r in results}
    usage["answering_model"] = models.pop() if len(models) == 1 else None
    for result in results:
        if result["status"] != "completed":
            return dict(result, usage=usage)
    findings, bodies, dispositions, kept = [], {}, [], set()
    for result in results:
        posted = {}
        for kind, field in (("submit_review", "comments"), ("create_check_run", "annotations")):
            for effect in result["effects"].get(kind, []):
                for note in effect[field]:
                    posted[note["finding"]] = (kind, note["body"])
        for finding in result["findings"]:
            if any(_same(finding, f) for f in findings):
                continue
            ref = "n%d" % (len(findings) + 1)
            findings.append(dict(finding, ref=ref))
            if finding["ref"] in posted:
                bodies[ref] = posted[finding["ref"]]
        for disposition in result["dispositions"]:
            if disposition["finding"] not in kept:
                kept.add(disposition["finding"])
                dispositions.append(disposition)
    effects = {}
    if any("submit_review" in r["effects"] for r in results):
        effects["submit_review"] = [{"id": "e1", "body": None, "comments": [
            {"finding": ref, "body": body} for ref, (kind, body) in bodies.items() if kind == "submit_review"]}]
    if any("create_check_run" in r["effects"] for r in results):
        effects["create_check_run"] = [{"id": "e2", "annotations": [
            {"finding": ref, "body": body} for ref, (kind, body) in bodies.items() if kind == "create_check_run"]}]
    cited = {f["criterion"] for f in findings if f["criterion"] is not None}
    coverage, judged = [], {}
    for result in results:
        for entry in result["coverage"]:
            judged.setdefault(entry["criterion"], []).append(entry)
    for criterion, entries in judged.items():
        if criterion in cited:
            coverage.append({"criterion": criterion, "verdict": "finding", "reason": None})
        elif any(e["verdict"] == "met" for e in entries):
            coverage.append({"criterion": criterion, "verdict": "met", "reason": None})
        else:
            coverage.append(dict(entries[0]))
    result = dict(results[0], findings=findings, effects=effects, dispositions=dispositions, coverage=coverage,
                  usage=usage)
    if shared.errors(result, "result") or not engine.sound(result, the_task):
        return engine.failed(the_task, "result_invalid", usage)
    return result



RUN_ID = re.compile(r"r_[0-9A-Z]{6,26}")


def from_folder(folder: str, out: str, base=None) -> list:
    """The first form's arguments from the folder `harness.read` wrote: its files by name, the Run id it holds, and the
    head it unpacked, `head`."""
    inside = os.path.realpath(str(pathlib.Path.cwd() if base is None else base))
    real = os.path.realpath(os.path.join(inside, folder))
    if not real.startswith(inside + os.sep):
        raise task.Refused("a path the job was given is outside the directory it runs in")
    with open(os.path.join(real, "run"), encoding="utf-8") as f:
        run = f.read().strip()
    if not RUN_ID.fullmatch(run):
        raise task.Refused("the Run id cannot be read")
    named = [os.path.join(folder, n) for n in ("record.json", "facts.json", "diff", "texts.json", "role.json",
                                               "findings.json")]
    return [named[0], run] + named[1:] + [out, os.path.join(folder, "head")]


def main(argv: list, job_env: dict) -> int:
    argv = argv or ["task", "result"]      # the workflow's form: the reader's folder, and the Result's
    if len(argv) not in (2, 8, 9):
        print("usage: python3 -m harness.run RECORD RUN FACTS DIFF TEXTS ROLE FINDINGS OUT [HEAD], or TASK OUT",
              file=sys.stderr)
        return 2
    try:
        if len(argv) == 2:
            argv = from_folder(argv[0], argv[1])
        digest = job(argv, job_env, configuration())
    except (task.Refused, OSError, ValueError) as err:
        print("harness.run: %s" % type(err).__name__, file=sys.stderr)
        return 1
    print("result.json %s" % digest)
    # The job's output, by the file GitHub names for a step's outputs: the digest alone, which `verify` and `apply`
    # take the Result by. Nothing else of the Result reaches it.
    if isinstance(job_env.get("GITHUB_OUTPUT"), str) and job_env["GITHUB_OUTPUT"]:
        with open(job_env["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            f.write("digest=%s\n" % digest)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:], dict(os.environ)))
