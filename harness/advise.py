"""The `run` job's advise step: each advisory Lens's reader is asked to read the change, and its Result is written
(decision 0224).

    python3 -m harness.advise TASK OUT

TASK is the folder `python3 -m harness.read` wrote; OUT the folder `python3 -m harness.unasked` made, or one this step
makes. For a review of a change that is no dependency's, the step asks each reader `config/harness.json` configures, in
the order `advisory` names them, once. It reads the diff and the Run's own files and nothing from GitHub, and it holds
one secret, the Azure key, under `ADVISORY_AZURE_KEY`. It writes
`advice.<lens>.json`, an `advice/1`, and its digest beside it, for every reader that can be asked: `completed`,
`incomplete` or `failed`. A reader whose name or settings build no `advice/1` is not asked, and has none.

`advice-cost.json`, the Run's `advice-cost/1`, is all the Controller reads of the Run, and `harness.unasked` wrote it
with no asks. A Run that is about to ask a reader can no longer say so. For now this step only takes that word back:
before its first request it removes the file, so a Run that asks leaves no cost file and a pass, finding none, counts
the Run's worst case (decision 0224, Spend). The change that follows this one has the step write the Run's own cost in
its place. A Run that asks nobody leaves the file as it was written.

The step never fails its job. A reader that cannot be asked, or does not answer, has a Result that says why by a code,
and anything this file did not foresee is the code `transport`, for that reader alone; the review then runs without
that reader. It asks nothing unless the pass record says the day's ceiling admits it, beside the Run's Decision: with
no such word the Result is `budget` (decision 0224, Spend). A prompt past the reader's `prompt_characters`, in bytes of
UTF-8 as decision 0243 prices it, is not asked: `too_large`.

Time. The readers share WHOLE seconds from the step's start, asked one after another: a reader's turn ends where only
the `share` of each reader after it that is to be asked is left, and the last runs to the step's end (trial P-78). A
share that cannot be read is none. A request waits the reader's `seconds`, or what is left of its turn where that is
less. Limits: a read of a response, and its cancel, wait as long as the ask that made it, so one sent near its turn's
end may run past it. No workflow runs the step yet.

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
from harness import shared, steps, task, unasked

ROOT = pathlib.Path(__file__).resolve().parent.parent
KEY = "ADVISORY_AZURE_KEY"
REVIEWING = "review-change"
INSTRUCTION = ("roles", "pr-review", "advisory-reader.md")
# The seconds the readers share, from the step's start: astra's 900 and kimi's 540 (trial P-78), the step's whole that
# tools/check_examples.py holds the readers' shares to. The workflow that runs the step is to give it a limit past it.
WHOLE = 1440
POLL = 10               # seconds between two reads of a response still running
RUNNING = ("queued", "in_progress")
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


def share_of(reader: dict) -> int:
    """A reader's `share` of the step, or none where it is not a whole number above nought: a bool is not one."""
    share = reader.get("share")
    return share if isinstance(share, int) and not isinstance(share, bool) and share > 0 else 0


def turn_of(later: list, until: float) -> float:
    """Where a reader's turn ends: where only the shares of `later`, the readers after it that are to be asked, are
    left of the step. With none, the step's end; never past it."""
    return until - sum(share_of(reader) for reader in later)


def lasted(began: float, clock) -> float:
    return round(clock() - began, 1)


def asks_of(sent: list) -> int:
    """The asks among what was sent, each counted when sent, since a request not answered may still be billed."""
    return min(2, sum(act in ("create", "chat") for act in sent))


def asked(send, reader: dict, request: dict, until: float, clock, sleep) -> tuple:
    """`(answer, asks)` for one reader: the request sent once; a
    response of the Responses API read until it has ended, and cancelled where it has not by `until`."""
    asks, answer = 1, send(request)
    body = answer.get("body")
    if reader["api"] != "responses" or answer.get("status") != 200 or not isinstance(body, dict):
        return answer, asks
    ident = body.get("id")
    while body.get("status") in RUNNING:
        if clock() + POLL >= until:
            send(azure.cancel(ident))       # not left to run on and be billed
            break
        sleep(POLL)
        answer = send(azure.read(ident))
        body = answer.get("body")
        if answer.get("status") != 200 or not isinstance(body, dict):
            break
    return answer, asks


def refusal(reader: dict, prompt: str, admitted: bool, key):
    """The code a reader is refused by before anything is sent, or None."""
    if not admitted:
        return "budget"
    if len(prompt.encode("utf-8")) > reader["prompt_characters"]:
        return "too_large"
    if not isinstance(key, str) or not key:
        return "no_key"
    return None


def due(reader, prompt, admitted: bool, key) -> bool:
    try:
        return refusal(reader, prompt, admitted, key) is None
    except Exception:       # NOSONAR a reader that cannot be read is not about to be asked
        return False


def one(reader: dict, told: dict, prompt: str, admitted: bool, key, until: float, sent: list, transport, clock,
        sleep) -> dict:
    """One reader's Result. `sent` is given each request's act as it is sent, for the caller that must count them."""
    began = clock()
    why = refusal(reader, prompt, admitted, key)
    if why is not None:
        return advice.unasked(told, why, 0, 0, shared.SCHEMAS)

    live = transport(reader["host"], key, min(reader["seconds"], max(1, int(until - began))))

    def send(request: dict) -> dict:
        sent.append(request["act"])
        return live.send(request)
    answer, asks = asked(send, reader, body_of(reader, told["effort"], prompt), until, clock, sleep)
    return advice.read(told, answer, asks, lasted(began, clock), shared.SCHEMAS)


def prompt_of(root: pathlib.Path, folder: str, diff: str) -> str:
    """The fixed instruction, the base's rules the reader's folder holds, and the whole diff."""
    told = root.joinpath(*INSTRUCTION).read_text(encoding="utf-8")
    try:
        with open(os.path.join(folder, "rules.json"), encoding="utf-8") as f:
            rules = json.load(f)
    except (OSError, ValueError, RecursionError):
        rules = {}
    rules = {name: text for name, text in rules.items() if isinstance(text, str)} if isinstance(rules, dict) else {}
    held = "\n\n".join("--- %s ---\n%s" % (name, rules[name]) for name in sorted(rules)) or "(none was read)"
    return told + DATA % (held, diff)


HELD = (unasked.COST,)      # what OUT may hold when the step takes it: what the first step wrote


def folder_of(base, out: str) -> str:
    """OUT: the folder `harness.unasked` made, or one made new; Stop `out_exists` for a link, a file, or a folder that
    holds anything but what that step left, a Result planted there or the task's own files among them."""
    real, path = steps.inside(base, out), os.path.join(os.path.realpath(str(base)), out)
    if not os.path.lexists(path):
        return steps.new_folder(base, out)
    if os.path.islink(path) or not os.path.isdir(path) or set(os.listdir(real)) - set(HELD):
        raise steps.Stop("out_exists")
    return real


def job(task_folder: str, out: str, env: dict, root: pathlib.Path = ROOT, base=None, transport=azure.Live,
        clock=time.monotonic, sleep=time.sleep) -> list:
    """Ask each reader and write its Result into OUT. Returns `(lens, digest)` for each written."""
    until = clock() + WHOLE
    base = pathlib.Path.cwd() if base is None else base
    folder = steps.inside(base, task_folder)
    with open(os.path.join(folder, "run"), encoding="utf-8") as f:
        run = f.read().strip()
    record = steps.read_json(base, os.path.join(task_folder, "record.json"))
    release = record["release"]
    made, written = folder_of(base, out), []

    def ask() -> None:
        facts = steps.read_json(base, os.path.join(task_folder, "facts.json"))
        entry = task.decision_of(record, run)
        if entry is None or entry["decision"]["admit"]["intent"] != REVIEWING or facts.get("class") == "dependency":
            return      # no reader is asked, and what the first step said of the Run stands
        config = json.loads((root / "config" / "harness.json").read_text())
        readers = config.get("readers", {})
        names = [name for name in config["advisory"] if name in readers]
        with open(os.path.join(folder, "diff"), "rb") as f:
            prompt = prompt_of(root, folder, f.read().decode("utf-8", errors="replace"))
        admitted, key = entry.get("advisory_ask") is True, env.get(KEY)
        asking = [lens for lens in names if due(readers[lens], prompt, admitted, key)]
        if asking:
            # Before the first request: the Run no longer says that it asked nobody.
            try:
                os.unlink(os.path.join(made, unasked.COST))
            except FileNotFoundError:
                pass
        for n, lens in enumerate(names):
            sent, told, began = [], None, clock()
            try:
                reader = readers[lens]
                rows = facts["changed_paths"]
                paths = [name for row in rows for name in (row["path"], row["previous"]) if isinstance(name, str)]
                told = {"run": run, "release": release, "lens": lens, "content_id": facts["content_id"],
                        "changed_paths": sorted({row["path"] for row in rows}), "api": reader["api"],
                        "deployment": reader["deployment"], "model": reader["model"],
                        "effort": effort_of(reader, paths), "characters": config["texts"]["characters"],
                        "usd_per_million": reader["usd_per_million"]}
                advice.unasked(told, "transport", 0, 0, shared.SCHEMAS)     # no advice/1 can be built: it is not asked
                turn = turn_of([readers[later] for later in names[n + 1:] if later in asking], until)
                result = one(reader, told, prompt, admitted, key, turn, sent, transport, clock, sleep)
            except Exception:       # NOSONAR whatever one reader's read raises is that reader's Result, and no other's
                try:
                    result = advice.unasked(told, "transport", asks_of(sent), lasted(began, clock), shared.SCHEMAS)
                except Exception:   # NOSONAR nothing can be said for this Lens
                    continue
            data = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
            digest = "sha256:" + hashlib.sha256(data).hexdigest()
            steps.write(made, "advice.%s.json" % lens, data)
            steps.write(made, "advice.%s.sha256" % lens, (digest + "\n").encode())
            written.append((lens, digest))
    ask()
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
