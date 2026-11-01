"""The Engine's check end to end (decision 0106): the install and one review, on a real runner, for one model call.

A workflow of the canary repo runs it on a checkout of this repo's `main`, weekly and before each cut: `install`, then
`review`, each a step, the model's credential in `review` alone. `install` runs the lines the eval job and the Run's jobs
hold word for word, so that a line taken from them is taken from this check too: a copy in the canary's workflow would
stay green. `review` asks the eval job's own `assess` about one case, and it is red unless the CLI answered.

Its case is the repo's own example, never one of the held-out set, so it may do what the eval job's steps may not: when
the CLI fails it prints the end of what the CLI said, which is what names the cause. It holds nothing else to say: a case
the model answered and missed is a matter for the eval, and is green here."""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time

from harness import eval as job, run as live
from harness.eval import run as step
from tools import check_workflows

# No Release is judged here; a Result must still name one.
RELEASE = "factory/v0.0.1"
# Enough of what a failing CLI said to name its cause: the line that named the missing package is about 200.
TAIL = 600


def install(env: dict, call=subprocess.run) -> int:
    """Run this checkout's install of the CLI, at its pin and by its checksum, as a workflow's `run:` block is run."""
    version = json.loads((job.ROOT / "config" / "harness.json").read_text())["engine"]["version"]
    given = dict(env, CLI_VERSION=version, CLI_CHECKSUM=check_workflows.CLI_CHECKSUMS[version])
    return call(["bash", "-e", "-c", "\n".join(check_workflows.CLI_INSTALL_RUN)], env=given, check=False).returncode


def told(call):
    """`call`, the CLI's, saying the end of what the CLI said when it failed."""
    def asked(args, env, timeout):
        done = call(args, env, timeout)
        if done.returncode != 0:
            print("the CLI exited %d: %s" % (done.returncode, done.stderr[-TAIL:]))
        return done
    return asked


def review(env: dict, call=live.cli_call, clock=time.time) -> int:
    """One review by the eval job's path: 0 if the CLI answered and its answer was read and scored, and 1 otherwise. A
    scorer that raises is no answer either, and the step fails on it."""
    case = json.loads((job.ROOT / "examples" / "eval-case.json").read_text())
    content = "sha256:" + hashlib.sha256(case["diff"].encode("utf-8")).hexdigest()
    case["facts"]["content_id"] = content
    results = []
    reviewer = step.reviewer(env, RELEASE, int(clock()), told(call), clock)

    def answered(given: dict) -> dict:
        results.append(reviewer(given))
        return results[-1]

    with tempfile.TemporaryDirectory() as scratch:
        place = pathlib.Path(scratch)
        (place / "cases").mkdir()
        (place / "cases" / ("%s.json" % case["id"])).write_text(json.dumps(case), encoding="utf-8")
        found = {"role": case["role"], "intent": case["intent"], "cases": [{"id": case["id"]}]}
        verdict, reasons = job.assess(found, {case["id"]: None}, place, answered)[case["id"]]
    status = results[0].get("status") if results else None
    print("status %s, verdict %s, reasons %s" % (status, verdict, ",".join(reasons) or "none"))
    return 0 if status == "completed" else 1


if __name__ == "__main__":
    ACTS = {"install": install, "review": review}
    sys.exit(ACTS[sys.argv[1]](dict(os.environ)))
