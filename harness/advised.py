"""The advisory part of `apply`: each advisory Lens's Result shown as a check run that is always `neutral` (decision
0224, "What is shown"). `harness/apply_step.py` calls `run` last, once the Run's record and its outcome are written and
its read token revoked; nothing here changes either, and nothing here can keep the step past its time.

    python3 -m harness.advised WORK

Three parts. `asked` decides, with no network, which Lens has a Result to show and builds its check run. `run` writes
those into WORK, a folder of the step's own, starts this module as a child with the Role App's key and nothing else,
and kills it at a hard deadline, so the step never waits on the network after the Run's files are written. The child,
`main`, mints a token of the check run's need alone, writes each check run through the advisory allowlist, revokes the
token, and says what it did a line at a time as it goes, which `told` reads back whatever became of the child:

    began                   before the token is asked for
    unminted                no token was minted: `identity` refused before GitHub was asked for one
    <lens> <code> [<key>]   one Lens's check run: a code of `adapters/advice.py`'s, and its key where it was read back
    revoked | unrevoked     whether GitHub confirmed the token revoked

A Lens the child did not report is `out_of_time`. A child that began and did not say `revoked`, killed or not, leaves
the token's state unknown: every Lens it was asked for is `token_not_revoked`, with the key of any it had shown. So
does a mint GitHub was asked for and refused, answered other than as asked, or that failed for a cause not foreseen:
GitHub may have made a token all the same, and `unrevoked` is said, never `unminted`.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time

from adapters import advice, effects, identity
from adapters.github import TIMEOUT, Live
from controller import configuration
from harness import shared, steps
from harness.steps import Stop

APP = "pr-review"
KEY = "PR_REVIEW_APP_KEY"
REVIEWING = "review-change"     # the Intent whose Run the advisory Lenses read for
COMMAND = [sys.executable, "-m", "harness.advised"]
# The time, in seconds. A request waits at most TIMEOUT, 20, on each read of its socket, which is no bound on a request:
# the bound is the kill. The step has 240 (`Apply the Result` in run-jobs.yml). The child is killed after CHILD, or
# sooner so that RESERVE is left the step to write its record and end; it is not started with less than LEAST, what a
# mint of two requests, one check run of three and a revocation of one need. The child itself begins no Lens that
# could not end, and be revoked, inside its time: three requests and one, and five seconds to say so.
CHILD, RESERVE, LEAST = 150, 30, 6 * TIMEOUT + 10
ONE = 4 * TIMEOUT + 5
MOST = 4 * 1024 * 1024      # the bytes of what the child is asked and of what it says that are read
# What `identity` refuses before GitHub is asked to mint: with one of these, and no other, no token was made.
BEFORE = frozenset({"key_unreadable", "key_cannot_sign", "app_unreadable", "effect_not_grantable", "effect_not_granted",
                    "installation_unreadable"})
LINE = re.compile(r"([a-z]{1,31}) ([a-z_]{1,40})(?: ([A-Za-z0-9_=:-]{1,100}))?")


def _file(base, folder, name: str, most: int):
    """At most `most` bytes of the file `name` in `folder`, or None. The folder is followed to where it really is, a
    link or not, and must lie inside `base`; the file itself is never a link: one is not opened."""
    try:
        opened = os.open(os.path.join(steps.inside(base, folder), name), os.O_RDONLY | os.O_NOFOLLOW)
        with open(opened, "rb") as f:
            return f.read(most)
    except (OSError, Stop, TypeError, ValueError):
        return None


def asked(base, folder, admit, ended: dict, held: dict) -> tuple:
    """`(said, reqs)`: a code for each advisory Lens the Factory asks that has none to show, `{lens: code}`, and the
    check run of each that has, `[(lens, request)]`. Neither for a Run no Decision admitted or of another Intent than
    a review. A change under the Run, by its outcome or by the facts read again, is `superseded` for every Lens; a Run
    the Factory faulted, `environment` or `capacity`, is `run_not_whole`; an item not read again `item_not_read`. Else
    each Result is read from `folder`, it and its digest bounded, and held (`advice.held`): one that fails is its code."""
    if admit is None or admit["intent"] != REVIEWING:
        return {}, []
    asks = steps.read_json(steps.ROOT, os.path.join("config", "harness.json"))
    names = [lens for lens in asks["advisory"] if lens in asks.get("readers", {})]
    facts, head = held["item"][:2] if "item" in held else (None, None)
    every = "superseded" if ended["outcome"] == "superseded" else "run_not_whole" if ended["outcome"] not in (None, "item") \
        else "item_not_read" if facts is None \
        else "superseded" if facts["state"] != "open" or facts["content_id"] != admit["content_id"] else None
    if every is not None:
        return {lens: every for lens in names}, []
    said, reqs = {}, []
    for lens in names:
        data = _file(base, folder, "advice.%s.json" % lens, advice.LARGEST + 1)
        digest = _file(base, folder, "advice.%s.sha256" % lens, 128)
        result, said[lens] = advice.held(data, digest, lens, names, admit, shared.SCHEMAS)
        if result is not None:
            output, ids = advice.shown(result)
            reqs.append((lens, {"commit": head, "name": advice.CHECK % lens, "conclusion": "neutral",
                                "external_id": "%s:%s" % (admit["run"], lens), "output": output,
                                "annotations": [{"finding": ident} for ident in ids]}))
    return said, reqs


def told(out, lenses: list) -> dict:
    """`{lens: (code, key)}` for each Lens the child was asked, from what it said, `out`, however it ended."""
    lines = out.decode("utf-8", errors="replace").split("\n")[:-1] if isinstance(out, bytes) else []
    said = {}
    for line in lines:
        one = LINE.fullmatch(line)
        # A check run read back is said with its key, and nothing else is: a line that says otherwise says nothing.
        if one and one.group(1) in lenses and one.group(1) not in said and one.group(2) in advice.CODES \
                and (one.group(2) == "shown") == (one.group(3) is not None):
            said[one.group(1)] = (one.group(2), one.group(3))
    if "unminted" in lines and "unrevoked" not in lines:
        return {lens: ("token_not_minted", None) for lens in lenses}
    if "began" not in lines:
        return {lens: ("out_of_time", None) for lens in lenses}     # nothing was asked of GitHub
    if "revoked" not in lines or "unrevoked" in lines:
        # The token's state is not known: it was asked for, and GitHub was not heard to revoke it.
        return {lens: ("token_not_revoked", said.get(lens, (None, None))[1]) for lens in lenses}
    return {lens: said.get(lens, ("out_of_time", None)) for lens in lenses}


def run(base, folder, work: str, admit, ended: dict, held: dict, environ: dict, left, spawn=subprocess.run) -> list:
    """`(lens, code, key)` for each advisory Lens the Factory asks, for `advice.recorded`. `work` is a new folder of
    the step's own; `left()` the seconds the step still has. The child is given the Role App's key in its environment
    and nothing else of the step's, the folder's path on its command line, and its time; it is killed at the deadline."""
    said, reqs = asked(base, folder, admit, ended, held)
    lenses = [lens for lens, _ in reqs]
    seconds = min(CHILD, int(left()) - RESERVE)
    if reqs and seconds < LEAST:
        heard = {lens: ("out_of_time", None) for lens in lenses}
    elif reqs:
        made = steps.new_folder(base, work)
        steps.write(made, "asked.json", {"item": admit["item"], "head": held["item"][1], "run": admit["run"],
                                         "release": admit["release"], "seconds": seconds,
                                         "asked": [{"lens": lens, "request": req} for lens, req in reqs]})
        try:
            out = spawn(COMMAND + [made], cwd=str(steps.ROOT), env={KEY: environ.get(KEY) or "", "PATH": environ.get("PATH", "")},
                        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=seconds,
                        check=False).stdout
        except subprocess.TimeoutExpired as killed:
            out = killed.stdout
        except OSError:
            out = None
        heard = told(out[:MOST] if isinstance(out, bytes) else None, lenses)
    return [(lens,) + (heard[lens] if lens in lenses else (code, None)) for lens, code in said.items()]


def main(argv: list, environ: dict, connect=Live, clock=time.monotonic, say=None) -> int:
    """The child. It reads what it is asked from the folder it is given, says each thing it does as it does it, and
    always ends 0: what it could not do is what it did not say. It says codes and keys alone."""
    say = say or (lambda line: print(line, flush=True))
    began = clock()
    try:
        with open(os.open(os.path.join(argv[0], "asked.json"), os.O_RDONLY | os.O_NOFOLLOW), "rb") as f:
            asking = json.loads(f.read(MOST).decode("utf-8"))
        config = configuration.load(steps.ROOT, asking["release"], APP)
        names = steps.read_json(steps.ROOT, os.path.join("config", "harness.json"))["advisory"]
        item, lenses = asking["item"], [one["lens"] for one in asking["asked"] if one["lens"] in names]
        say("began")
        try:
            transport, revoke = identity.from_key(
                config["app"], config["controller"]["home"]["repo"],
                identity.permissions(config["app"], config["needs"], ["create_check_run"]), environ.get(KEY), int(time.time()),
                connect)
        except Exception as refused:    # NOSONAR a mint that failed, for whatever cause, is said: nothing was written
            say("unminted" if isinstance(refused, identity.Refused) and str(refused) in BEFORE else "unrevoked")
            return 0
        try:
            for one in asking["asked"]:
                if asking["seconds"] - (clock() - began) < ONE:
                    continue        # not said, so `out_of_time`: the token is still revoked
                try:
                    back = effects.advisory_write(transport, item, asking["head"], lenses, asking["run"], one["request"],
                                                  config["app"]["name"] + "[bot]")
                except Exception:   # NOSONAR a write that raises, foreseen or not, is a code, and the token is revoked
                    back = {"state": "raised"}
                state, key = back.get("state"), back.get("key")
                if state in ("applied", "already_applied") and isinstance(key, str) and advice.KEY.fullmatch(key):
                    say("%s shown %s" % (one["lens"], key))
                else:
                    say("%s %s" % (one["lens"], {"sent": "not_read_back", "raised": "write_raised"}.get(state, "not_written")))
        finally:
            try:
                gone = revoke() is True
            except Exception:   # NOSONAR a revocation that raises is one GitHub did not confirm
                gone = False
            say("revoked" if gone else "unrevoked")
    except Exception:   # NOSONAR the child says codes alone; what it did not say, its parent records
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:], dict(os.environ)))
