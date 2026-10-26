"""The `verify` job: what is checked of one Run's Result before `apply` may write it, with no secret and no cache
(#196's ruling 7; design sections 2.3 and 3.10).

    python3 -m harness.verify RESULT OUT

RESULT is the folder the Result was downloaded into, by the artifact id `run` reported; OUT a new folder. The Result is
taken by the digest `run` reported, `RUN_DIGEST`, and held to `result/1`: a Result of other bytes, or one that is no
Result, fails the job, so `apply` writes nothing. An Intent that pushes nothing, as the review Intent, has no code of its
own to check: its `checks` are `not_run`, never `passed` (L-54). The checks for code come with the fix Intent. OUT holds
`verdict.json`, `verdict/1`: the Run, its Release, the digest and the checks, and no field of the Result."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys

from harness import shared, steps
from harness.steps import Stop

DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


def step(argv: list, environ: dict, base) -> str:
    if len(argv) != 2:
        raise Stop("usage: python3 -m harness.verify RESULT OUT")
    found, out = argv
    reported = environ.get("RUN_DIGEST")
    if not isinstance(reported, str) or not DIGEST.fullmatch(reported):
        raise Stop("digest_unreadable")
    try:
        with open(steps.inside(base, os.path.join(found, "result.json")), "rb") as f:
            data = f.read()
    except OSError:
        raise Stop("result_unreadable") from None
    if "sha256:" + hashlib.sha256(data).hexdigest() != reported:
        raise Stop("result_not_the_runs")
    try:
        result = json.loads(data.decode("utf-8"))
    except ValueError:
        raise Stop("result_unreadable") from None
    if shared.errors(result, "result"):
        raise Stop("result_unreadable")
    verdict = {"schema": "verdict/1", "run": result["run"], "release": result["release"], "digest": reported,
               "checks": "not_run"}
    if shared.errors(verdict, "verdict"):
        raise Stop("result_unreadable")
    steps.write(steps.new_folder(base, out), "verdict.json", verdict)
    return "verified %s, checks not_run" % reported


if __name__ == "__main__":
    steps.exit_with(step, sys.argv[1:], dict(os.environ), os.getcwd())
