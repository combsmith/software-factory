"""The `apply` job's last step, run whatever failed before it: the Run's `outcome/1`, which the pass reads for a Run
that did not succeed (design section 3.10; #196's ruling 7).

    python3 -m harness.outcome NAME APPLIED OUT

NAME is the Run's run-name, APPLIED the folder `harness.apply_step` wrote into, OUT a new folder. The outcome `apply`
recorded is kept when it is this Run's and this Release's, the one its checkout carries (`steps.release`); when it is missing or is not, as when the step
before failed or never ran, the Run ends `environment`, `apply_failed`, so that no Run that died leaves nothing. OUT
holds `outcome.json` alone. An outcome that names a fault fails the step, by its code, once it is written, so that the
run concludes as it ended and the pass reads it (`adapters/records.py` reads a failed Run's outcome alone); the upload
after it runs whatever failed."""
from __future__ import annotations

import os
import sys

from adapters import records
from controller import configuration
from harness import shared, steps
from harness.steps import Stop


def step(argv: list, environ: dict, base) -> str:
    argv = steps.given(argv, environ, ("NAME",), ("applied", "outcome"))
    if len(argv) != 3:
        raise Stop("usage: python3 -m harness.outcome NAME APPLIED OUT")
    name, applied, out = argv
    parts = records.named(name)
    if parts is None:
        raise Stop("run_unreadable")
    release = steps.release()
    try:
        kept = steps.read_json(base, os.path.join(applied, "outcome.json"))
    except Stop:
        kept = None
    if shared.errors(kept, "outcome") or (kept["run"], kept["release"]) != (parts["run"], release):
        kept = {"schema": "outcome/1", "run": parts["run"], "release": release, "outcome": "environment",
                "reason": "apply_failed"}
    steps.write(steps.new_folder(base, out), "outcome.json", kept)
    # A Run that did not succeed must conclude so, or the pass never reads its outcome (section 3.10).
    if kept["outcome"] is not None:
        raise Stop(kept["reason"] or kept["outcome"])
    return "outcome none"


if __name__ == "__main__":
    steps.exit_with(step, sys.argv[1:], dict(os.environ), os.getcwd())
