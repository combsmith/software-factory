"""The `apply` job's last step, run whatever failed before it: the Run's `outcome/1`, which the pass reads for a Run
that did not succeed (design section 3.10; #196's ruling 7).

    python3 -m harness.outcome NAME APPLIED OUT [TASK]

NAME is the Run's run-name, APPLIED the folder `harness.apply_step` wrote into, OUT a new folder, and TASK, when
given, the folder the `run` job's reader wrote; with no argument, the workflow's form, NAME is the environment's and
the folders are `applied`, `outcome` and `reader-outcome`, where the run job's `reader-outcome` artifact is downloaded
when there is one. A Run the reader found on another Release than its pass's left in TASK its own `outcome/1`,
`superseded`, `release_moved` (#197's ruling 8); its `run` job failed by that code, so `apply` read nothing and said
`run_failed`, and the reader's outcome, when it is this Run's and this Release's, is the one kept. The outcome `apply`
recorded is kept when it is this Run's and this Release's, the one its checkout carries (`steps.release`); when it is
missing or is not, as when the step before failed or never ran, the Run ends `environment`, `apply_failed`, so that no
Run that died leaves nothing. OUT holds `outcome.json` alone. An outcome that names a fault fails the step, by its
code, once it is written, so that the run concludes as it ended and the pass reads it (`adapters/records.py` reads a
failed Run's outcome alone); the upload after it runs whatever failed."""
from __future__ import annotations

import os
import sys

from adapters import records
from controller import configuration
from harness import shared, steps
from harness.steps import Stop


MOVED = ("superseded", "release_moved")


def _read(base, folder: str):
    try:
        return steps.read_json(base, os.path.join(folder, "outcome.json"))
    except Stop:
        return None


def step(argv: list, environ: dict, base) -> str:
    argv = steps.given(argv, environ, ("NAME",), ("applied", "outcome", "reader-outcome"))
    if len(argv) not in (3, 4):
        raise Stop("usage: python3 -m harness.outcome NAME APPLIED OUT [TASK]")
    name, applied, out = argv[:3]
    parts = records.named(name)
    if parts is None:
        raise Stop("run_unreadable")
    release = steps.release()
    try:
        kept = steps.read_json(base, os.path.join(applied, "outcome.json"))
    except Stop:
        kept = None
    moved = _read(base, argv[3]) if len(argv) == 4 else None
    if not shared.errors(moved, "outcome") and (moved["run"], moved["release"]) == (parts["run"], release) \
            and (moved["outcome"], moved["reason"]) == MOVED:
        kept = moved
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
