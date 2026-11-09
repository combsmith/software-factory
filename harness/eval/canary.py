"""The Engine's check end to end (decision 0106): the install and one review, on a real runner, for one model call.

A workflow of the canary repo runs it on a checkout of this repo's `main`, weekly and before each cut: `install`, then
`review`, each a step, the model's credential in `review` alone. `install` runs the lines the eval job and the Run's jobs
hold word for word, so that a line taken from them is taken from this check too: a copy in the canary's workflow would
stay green. `review` asks the eval job's own `assess` about one case, and it is red unless the CLI answered. The eval
job's steps are its own modules; this is no step of that job, and is run by another repo's workflow.

Its case is the repo's own example, never one of the held-out set, so it may do what the eval job's steps may not: when
the CLI fails it prints the end of what the CLI said, which is what names the cause. It holds nothing else to say: a case
the model answered and missed, or refused, is a matter for the eval, and is green here."""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

from harness import engine, eval as job, run as live
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
    """`call`, the CLI's, saying the end of what the CLI said when it failed, its credential taken out first: the log is
    public, and a slice could start inside the value, where a runner's masking would not know it."""
    def asked(args, env, timeout, **given):
        done = call(args, env, timeout, **given)
        if done.returncode != 0:
            said = done.stderr.replace(env[engine.CREDENTIAL_NAME], "***")
            print("the CLI exited %d: %s" % (done.returncode, said[-TAIL:]))
        return done
    return asked


def head_of(data: bytes, folder: pathlib.Path, ident: str, transport):
    """The example's head, its commit's tarball read through `transport`, with no credential, from this repo, which is
    public, and unpacked into `folder` under its id; or `head_unreadable`. The eval job reads a case's head from the
    held-out home instead, pinned by the case (issue 611): the example is no case of the home, and pins none it keeps."""
    from harness import head
    case = json.loads(data)
    repo, sha = case["facts"]["item"]["repo"], case["head"]
    folder.mkdir(mode=0o700, exist_ok=True)
    try:
        head.unpack(head.fetch(transport, repo, sha), sha, job.within(folder, ident))
    except (head.Refused, OSError, job.Stop):
        shutil.rmtree(str(folder / ident), ignore_errors=True)
        return "head_unreadable"
    return None


def review(env: dict, call=live.cli_call, clock=time.time, heads=None) -> int:
    """One review by the eval job's path: 0 if the CLI answered in a status the Engine may write, its answer read and
    scored, and 1 otherwise, a `failed` Result among them. A scorer that raises fails the step. The example's head is
    read through `heads`, by default with no credential, from this public repo (decision 0138); the eval job reads a case's
    from the held-out home instead (issue 611)."""
    case = json.loads((job.ROOT / "examples" / "eval-case.json").read_text())
    content = "sha256:" + hashlib.sha256(case["diff"].encode("utf-8")).hexdigest()
    case["facts"]["content_id"] = content
    results = []
    # The head apart from the case, as the eval job keeps them (issue 623).
    with tempfile.TemporaryDirectory() as scratch, tempfile.TemporaryDirectory() as unpacked:
        place = pathlib.Path(scratch)
        reviewer = step.reviewer(env, RELEASE, int(clock()), told(call), clock, pathlib.Path(unpacked))

        def answered(given: dict) -> dict:
            results.append(reviewer(given))
            return results[-1]
        (place / "cases").mkdir()
        data = json.dumps(case).encode("utf-8")
        (place / "cases" / ("%s.json" % case["id"])).write_bytes(data)
        found = {"role": case["role"], "intent": case["intent"], "cases": [{"id": case["id"]}]}
        if heads is None:
            from adapters import github
            heads = github.Live.anonymous()
        fetched = head_of(data, pathlib.Path(unpacked), case["id"], heads)
        verdict, reasons = job.assess(found, {case["id"]: fetched}, place, answered)[case["id"]]
    status = results[0].get("status") if results else None
    print("status %s, verdict %s, reasons %s" % (status, verdict, ",".join(reasons) or "none"))
    return 0 if status in engine.ENGINE_WRITES else 1


if __name__ == "__main__":
    ACTS = {"install": install, "review": review}
    sys.exit(ACTS[sys.argv[1]](dict(os.environ)))
