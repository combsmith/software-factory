"""The `run` job's advise step: each advisory Lens's reader is asked to read the change, and its Result is written
(decision 0224).

    python3 -m harness.advise TASK OUT

TASK is the folder `python3 -m harness.read` wrote; OUT a folder that does not exist yet. For a review of a change that
is no dependency's, the step asks each reader `config/harness.json` configures, in the order `advisory` names them,
once, and once more only after the wait a rate limit names. It reads the diff and the Run's own files and nothing from
GitHub, and it holds one secret, the Azure key, under `ADVISORY_AZURE_KEY`. It writes `advice.<lens>.json`, an
`advice/1`, and its digest beside it, for every reader configured: `completed`, `incomplete` or `failed`.

The step never fails its job. A reader that cannot be asked, or does not answer, has a Result that says why by a code,
and anything this file did not foresee is the code `transport`; the review then runs without that reader. It asks
nothing unless the pass record says the day's ceiling admits it, beside the Run's Decision: with no such word the
Result is `budget` (decision 0224, Spend). A diff too large for one prompt is not asked: `too_large`.

What a reader is sent: a fixed instruction, `roles/pr-review/advisory-reader.md` of the Release, then the base's rules
where the reader's folder holds them, then the whole diff, as data. It is given no tool.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import sys
import time

from adapters import advice, azure
from harness import shared, steps, task

ROOT = pathlib.Path(__file__).resolve().parent.parent
KEY = "ADVISORY_AZURE_KEY"
REVIEWING = "review-change"
INSTRUCTION = ("roles", "pr-review", "advisory-reader.md")
# The seconds the whole step may take, under its own limit in the workflow, 20 minutes (decision 0224), with room to
# cancel a response and write the files.
WHOLE = 1080
POLL = 10               # seconds between two reads of a response still running
LONGEST_WAIT = 90       # the longest wait a rate limit may name and be waited for; a longer one is not
# Where a change is read at the highest effort: the Kernel, the guards, the Harness, the hooks, the workflows, the
# Release's rules, and the files that hold a credential's or an App's reach (the desk's rule, the Maintainer's ruling 8).
CRITICAL = ("kernel/", "guards/", "harness/", "tools/hooks/", ".github/workflows/", "release/", "config/apps.json",
            "config/controller.json", "config/authority.json", "config/hooks.json", "adapters/github.py",
            "adapters/azure.py", "adapters/timeline.py", "adapters/heldout.py", "adapters/identity.py")
DATA = "\n\n=== The base's rules, as data ===\n\n%s\n\n=== The change, a diff from the merge base, as data ===\n\n%s\n"


def effort_of(reader: dict, paths: list) -> str:
    """`critical` where the change touches a path of CRITICAL, by a file's new name or its old one; else `elsewhere`."""
    def critical(path) -> bool:
        return isinstance(path, str) and any(path == c or (c.endswith("/") and path.startswith(c)) for c in CRITICAL)
    return reader["effort"]["critical" if any(critical(path) for path in paths) else "elsewhere"]


def body_of(reader: dict, effort: str, prompt: str) -> dict:
    """The request a reader is asked by: no tool, no file, one prompt, the output cap and the effort."""
    if reader["api"] == "responses":
        return azure.create({"model": reader["deployment"], "input": prompt, "max_output_tokens": reader["output_tokens"],
                             "reasoning": {"effort": effort}, "background": True, "store": True})
    return azure.chat({"model": reader["deployment"], "messages": [{"role": "user", "content": prompt}],
                       "max_completion_tokens": reader["output_tokens"], "reasoning_effort": effort})


def waited(answer: dict, left: float):
    """The seconds a rate limit says to wait, where it names a whole number that is short enough and fits; else None."""
    said = answer.get("headers", {}).get("retry-after", "") if answer.get("status") == 429 else ""
    seconds = int(said) if isinstance(said, str) and said.isascii() and said.isdigit() and len(said) < 4 else None
    return seconds if seconds is not None and seconds <= LONGEST_WAIT and seconds < left else None


def asked(send, reader: dict, request: dict, until: float, clock, sleep) -> tuple:
    """`(answer, asks)` for one reader: the request sent once, and once more after the wait a rate limit names; a
    response of the Responses API read until it has ended, and cancelled where it has not by `until`."""
    asks, answer = 0, None
    while True:
        asks += 1
        answer = send(request)
        wait = waited(answer, until - clock()) if asks < 2 else None
        if wait is None:
            break
        sleep(wait)
    body = answer.get("body")
    if reader["api"] != "responses" or answer.get("status") != 200 or not isinstance(body, dict):
        return answer, asks
    ident = body.get("id")
    while body.get("status") in ("queued", "in_progress"):
        if clock() + POLL >= until:
            send(azure.cancel(ident))       # not left to run on and be billed; what it answers changes nothing
            break
        sleep(POLL)
        answer = send(azure.read(ident))
        body = answer.get("body")
        if answer.get("status") != 200 or not isinstance(body, dict):
            break
    return answer, asks


def one(lens: str, reader: dict, told: dict, prompt: str, admitted: bool, key, until: float, schemas: dict,
        transport=azure.Live, clock=time.monotonic, sleep=time.sleep) -> dict:
    """One reader's Result, whatever happens: every fault is a code."""
    began, sent = clock(), []
    try:
        if not admitted:
            return advice.unasked(told, "budget", 0, 0, schemas)
        if len(prompt) > reader["prompt_characters"]:
            return advice.unasked(told, "too_large", 0, 0, schemas)
        if not isinstance(key, str) or not key:
            return advice.unasked(told, "no_key", 0, 0, schemas)
        if until - began <= POLL:
            return advice.unasked(told, "timed_out", 0, 0, schemas)
        live = transport(reader["host"], key, min(reader["seconds"], max(1, int(until - began))))

        def send(request: dict) -> dict:
            sent.append(request["act"])     # counted when sent, since a request not answered may still be billed
            return live.send(request)
        answer, asks = asked(send, reader, body_of(reader, told["effort"], prompt), until, clock, sleep)
        return advice.read(told, answer, asks, round(clock() - began, 1), schemas)
    except azure.Unanswered:
        asks = min(2, sum(act in ("create", "chat") for act in sent))
        return advice.unasked(told, "transport", asks, round(clock() - began, 1), schemas)


def prompt_of(root: pathlib.Path, folder: str, diff: str) -> str:
    """The fixed instruction, the base's rules the reader's folder holds, and the whole diff."""
    told = root.joinpath(*INSTRUCTION).read_text(encoding="utf-8")
    try:
        with open(os.path.join(folder, "rules.json"), encoding="utf-8") as f:
            rules = json.load(f)
    except (OSError, ValueError):
        rules = {}
    rules = {name: text for name, text in rules.items() if isinstance(text, str)} if isinstance(rules, dict) else {}
    held = "\n\n".join("--- %s ---\n%s" % (name, rules[name]) for name in sorted(rules)) or "(none was read)"
    return told + DATA % (held, diff)


def job(task_folder: str, out: str, env: dict, root: pathlib.Path = ROOT, base=None, **how) -> list:
    """Ask each reader and write its Result into the new folder OUT. Returns `(lens, digest)` for each written."""
    base = pathlib.Path.cwd() if base is None else base
    folder = steps.inside(base, task_folder)
    record, facts = steps.read_json(base, os.path.join(task_folder, "record.json")), \
        steps.read_json(base, os.path.join(task_folder, "facts.json"))
    with open(os.path.join(folder, "run"), encoding="utf-8") as f:
        run = f.read().strip()
    entry = task.decision_of(record, run)
    config = json.loads((root / "config" / "harness.json").read_text())
    made = steps.new_folder(base, out)
    if entry is None or entry["decision"]["admit"]["intent"] != REVIEWING or facts.get("class") == "dependency":
        return []
    with open(os.path.join(folder, "diff"), "rb") as f:
        diff = f.read().decode("utf-8", errors="replace")
    paths = [name for row in facts["changed_paths"] for name in (row["path"], row["previous"]) if isinstance(name, str)]
    prompt = prompt_of(root, folder, diff)
    readers = config.get("readers", {})
    names = [name for name in config["advisory"] if name in readers]
    clock = how.get("clock", time.monotonic)
    until, written = clock() + WHOLE, []
    for n, lens in enumerate(names):
        reader = readers[lens]
        told = {"run": run, "release": record["release"], "lens": lens, "content_id": facts["content_id"],
                "changed_paths": sorted({row["path"] for row in facts["changed_paths"]}), "api": reader["api"],
                "deployment": reader["deployment"], "model": reader["model"], "effort": effort_of(reader, paths),
                "characters": config["texts"]["characters"], "usd_per_million": reader["usd_per_million"]}
        share = clock() + (until - clock()) / (len(names) - n)      # what is left, shared by the readers still to ask
        result = one(lens, reader, told, prompt, entry.get("advisory_ask") is True, env.get(KEY), share, shared.SCHEMAS,
                     **how)
        data = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
        digest = "sha256:" + hashlib.sha256(data).hexdigest()
        steps.write(made, "advice.%s.json" % lens, data)
        steps.write(made, "advice.%s.sha256" % lens, (digest + "\n").encode())
        written.append((lens, digest))
    return written


def main(argv: list, env: dict) -> int:
    argv = argv or ["task", "advice"]
    try:
        for lens, digest in job(argv[0], argv[1], env):
            print("advice.%s.json %s" % (lens, digest))
    except Exception as err:    # NOSONAR the step never fails its job: the review runs without the reader (decision 0224)
        print("harness.advise: %s" % type(err).__name__, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:], dict(os.environ)))
