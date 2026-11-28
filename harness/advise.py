"""The `run` job's advise step: each advisory Lens's reader is asked to read the change, and its Result is written
(decision 0224).

    python3 -m harness.advise TASK OUT

TASK is the folder `python3 -m harness.read` wrote; OUT the folder `python3 -m harness.unasked` made, or one this step
makes. For a review of a change that is no dependency's, the step asks each reader `config/harness.json` configures, in
the order `advisory` names them, once, and once more only after the wait a rate limit that billed nothing names. It
reads the diff and the Run's own files and nothing from GitHub, and it holds one secret, the Azure key, under `ADVISORY_AZURE_KEY`. It writes
`advice.<lens>.json`, an `advice/1`, and its digest beside it, for every reader that can be asked: `completed`,
`incomplete` or `failed`. A reader whose name or settings build no `advice/1` is not asked, and has none.

`advice-cost.json`, an `advice-cost/1`, is all the Controller reads of the Run, and it is true whenever the step is
stopped (the Factory Builder, 2026-11-19). `harness.unasked` wrote it with no asks. Before its first request this step
replaces it with the number of readers it is about to ask and a cost of null, which a pass counts at the worst case;
after the last reader, and whatever fault ended the step, it replaces it with the asks sent and their cost summed, null
where a reader that was asked has no count. An ask is counted as it is sent, and only then. A Run that asks nobody
leaves no asks and no cost. Nothing is made for a Run the step cannot name.

Attempts. The pass's yes is a grant for one attempt, the Run's first, which the day's ceiling was checked for; GitHub
names the attempt in `GITHUB_RUN_ATTEMPT`, and a re-run keeps the run's id. A later attempt asks no reader, whatever
its yes: each reader's Result is `rerun`, and the cost is nought, so that the pass does not count it at the worst case
(the Solution Architect, 2026-11-28). Limits: the first attempt's advice is not used again, and a person who wants it
again starts a new Run through the Controller, with a new yes against the ceiling. An attempt that cannot be read
asks nobody and writes nothing, and the pass counts the Run's worst case (the Factory Builder, 2026-11-28).

The step never fails its job. A reader that cannot be asked, or does not answer, has a Result that says why by a code,
and anything this file did not foresee is the code `transport`, for that reader alone; the review then runs without
that reader. It asks nothing unless the pass record says the day's ceiling admits it, beside the Run's Decision: with
no such word the Result is `budget` (decision 0224, Spend). A diff too large for one prompt is not asked: `too_large`.

Time. The readers share WHOLE seconds from the step's start, asked one after another: a reader's turn ends where only
the `share` of each reader after it that is to be asked is left, and the last runs to the step's end (trial P-78). A
share that cannot be read is none. A request waits the reader's `seconds`, or what is left of its turn where that is
less. No workflow runs the step yet.

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
LONGEST_WAIT = 90       # the longest wait a rate limit may name and be waited for; a longer one is not
RUNNING = ("queued", "in_progress")
ENDED = ("completed", "incomplete", "failed", "cancelled")      # a response in any other state may still be billed
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


def unbilled(answer: dict) -> bool:
    """Whether an answer is a rate limit that billed nothing: a 429 whose body counts no tokens. Azure bills no request
    it refuses for its rate, so the one more ask after it keeps a reader within the one billed ask a Run's worst case
    prices (decision 0243); a 429 that counts tokens may have been billed, and is not asked again."""
    body = answer.get("body")
    return answer.get("status") == 429 and not (isinstance(body, dict) and "usage" in body)


def waited(answer: dict, left: float):
    """The seconds a rate limit says to wait, where an unbilled 429 names a whole number that is short enough and fits
    the reader's time; else None."""
    said = answer.get("headers", {}).get("retry-after", "") if unbilled(answer) else ""
    seconds = int(said) if isinstance(said, str) and said.isascii() and said.isdigit() and len(said) < 4 else None
    return seconds if seconds is not None and seconds <= LONGEST_WAIT and seconds < left else None


def lasted(began: float, clock) -> float:
    return round(clock() - began, 1)


def asks_of(sent: list) -> int:
    """The asks among what was sent, each counted when sent, since a request not answered may still be billed."""
    return min(2, sum(act in ("create", "chat") for act in sent))


def asked(send, reader: dict, request: dict, until: float, clock, sleep) -> tuple:
    """`(answer, asks)` for one reader: the request sent once, and once more after the wait a rate limit names; a
    response of the Responses API read until it has ended, and cancelled wherever this leaves it not known to have."""
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
    ident, state = body.get("id"), body.get("status")
    try:
        while state in RUNNING and clock() + POLL < until:
            sleep(POLL)
            state = None        # not known again until this read is answered whole
            answer = send(azure.read(ident))
            body = answer.get("body")
            if answer.get("status") != 200 or not isinstance(body, dict):
                break
            state = body.get("status")
    finally:
        # Out of time, a read that failed or one not answered: the response is not left to run on and be billed.
        if state not in ENDED:
            try:
                send(azure.cancel(ident))
            except Exception:       # NOSONAR best effort: what a cancel answers, or that it does not, changes nothing
                pass
    return answer, asks


def refusal(reader: dict, prompt: str, barred, key):
    """The code a reader is refused by before anything is sent, or None. `barred` is the code the step bars every
    reader by, `rerun` or `budget`, or None."""
    if barred is not None:
        return barred
    if len(prompt) > reader["prompt_characters"]:
        return "too_large"
    if not isinstance(key, str) or not key:
        return "no_key"
    return None


def due(reader, prompt, barred, key) -> bool:
    try:
        return refusal(reader, prompt, barred, key) is None
    except Exception:       # NOSONAR a reader that cannot be read is not about to be asked
        return False


def one(reader: dict, told: dict, prompt: str, barred, key, until: float, sent: list, transport, clock,
        sleep) -> dict:
    """One reader's Result. `sent` is given each request's act as it is sent, for the caller that must count them."""
    began = clock()
    why = refusal(reader, prompt, barred, key)
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


def cost_of(run: str, attempt: int, release: str, spent: list) -> dict:
    """The Run's `advice-cost/1` from each reader's usage: the asks summed, and their cost, null where a reader that
    was asked gave none; no asks and no cost where no reader was asked."""
    asked_ = [usage for usage in spent if usage["asks"] > 0]
    known = all(usage["cost_usd"] is not None for usage in asked_)
    cost = round(sum(usage["cost_usd"] for usage in asked_), 6) if known else None
    return {"schema": "advice-cost/1", "run": run, "attempt": attempt, "release": release,
            "asks": sum(usage["asks"] for usage in spent), "cost_usd": cost}


HELD = (unasked.COST, unasked.COST + ".new")     # what OUT may hold when the step takes it: the cost, whole or half-written


def folder_of(base, out: str) -> str:
    """OUT: the folder `harness.unasked` made, or one made new; Stop `out_exists` for a link, a file, or a folder that
    holds anything but what that step left, a Result planted there or the task's own files among them."""
    real, path = steps.inside(base, out), os.path.join(os.path.realpath(str(base)), out)
    if not os.path.lexists(path):
        return steps.new_folder(base, out)
    if os.path.islink(path) or not os.path.isdir(path) or set(os.listdir(real)) - set(HELD):
        raise steps.Stop("out_exists")
    return real


def replace(folder: str, name: str, document: dict) -> None:
    """`name` in the step's folder, whole or as it was: written new beside it and moved over it, which follows no link
    at either name. `steps.write` makes a file new and never writes over one, so the one file this step rewrites is
    replaced here."""
    beside = name + ".new"
    try:
        os.unlink(os.path.join(folder, beside))     # what a step stopped half-way left
    except FileNotFoundError:
        pass
    steps.write(folder, beside, document)
    os.replace(os.path.join(folder, beside), os.path.join(folder, name))


def job(task_folder: str, out: str, env: dict, root: pathlib.Path = ROOT, base=None, transport=azure.Live,
        clock=time.monotonic, sleep=time.sleep) -> list:
    """Ask each reader and write its Result into OUT. Returns `(lens, digest)` for each written."""
    until = clock() + WHOLE
    base = pathlib.Path.cwd() if base is None else base
    folder = steps.inside(base, task_folder)
    with open(os.path.join(folder, "run"), encoding="utf-8") as f:
        run = f.read().strip()
    record = steps.read_json(base, os.path.join(task_folder, "record.json"))
    release, attempt = record["release"], unasked.attempt_of(env)
    if attempt is None:
        # Never taken for the first, which could ask twice on one yes: no reader is asked and no cost is written, so
        # the pass counts the Run's worst case (the Factory Builder, 2026-11-28).
        raise steps.Stop("attempt_unreadable")
    if shared.errors(cost_of(run, attempt, release, []), "advice-cost"):
        raise steps.Stop("run_unnamed")         # before anything is made: no folder is left for a Run with no name
    # `ledger` holds, for each reader begun, what was sent to it and its usage once it has a Result. One with none
    # counts its asks at a cost not known, so the file is true wherever the step stops.
    made, ledger, written = folder_of(base, out), [], []

    def ask() -> None:
        facts = steps.read_json(base, os.path.join(task_folder, "facts.json"))
        entry = task.decision_of(record, run)
        if entry is None or entry["decision"]["admit"]["intent"] != REVIEWING or facts.get("class") == "dependency":
            return      # no reader is asked, and the cost file says so
        config = json.loads((root / "config" / "harness.json").read_text())
        readers = config.get("readers", {})
        names = [name for name in config["advisory"] if name in readers]
        try:
            with open(os.path.join(folder, "diff"), "rb") as f:
                prompt = prompt_of(root, folder, f.read().decode("utf-8", errors="replace"))
        except Exception:       # NOSONAR with no prompt each reader has a Result, `transport`, and none is asked
            prompt = None
        # A re-run asks no reader, whatever its yes: the yes was a grant for the Run's first attempt alone, which the
        # day's ceiling was checked for (the Solution Architect, 2026-11-28).
        barred = "rerun" if attempt > 1 else None if entry.get("advisory_ask") is True else "budget"
        key = env.get(KEY)
        asking = [lens for lens in names if due(readers[lens], prompt, barred, key)]
        if asking:
            # Before the first request: a step stopped from here on has said how many readers it set out to ask.
            replace(made, unasked.COST, dict(cost_of(run, attempt, release, []), asks=len(asking), cost_usd=None))
        for n, lens in enumerate(names):
            sent, told, began = [], None, clock()
            ledger.append([sent, None])
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
                result = one(reader, told, prompt, barred, key, turn, sent, transport, clock, sleep)
            except Exception:       # NOSONAR whatever one reader's read raises is that reader's Result, and no other's
                try:
                    result = advice.unasked(told, "transport", asks_of(sent), lasted(began, clock), shared.SCHEMAS)
                except Exception:   # NOSONAR nothing can be said for this Lens; the ledger still counts its asks
                    continue
            ledger[-1][1] = result["usage"]
            data = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
            digest = "sha256:" + hashlib.sha256(data).hexdigest()
            try:
                steps.write(made, "advice.%s.json" % lens, data)
                steps.write(made, "advice.%s.sha256" % lens, (digest + "\n").encode())
            except Exception:       # NOSONAR a Result that cannot be written is not claimed; the next reader is asked
                continue
            written.append((lens, digest))
    try:
        ask()
    finally:
        # What the Controller's pass reads of this Run, and all it reads: how many requests were sent and what they
        # cost, summed here from the tokens each answer counted and the configured prices, and never from a reader's
        # text. A cost is null where a reader that was asked gave no count, so that it is never taken for nought.
        replace(made, unasked.COST, cost_of(run, attempt, release, [
            usage or {"asks": asks_of(sent), "cost_usd": None} for sent, usage in ledger]))
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
