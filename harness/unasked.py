"""The step a Run is to take before any other: the Run says that no advisory reader has been asked (decision 0224; the
Factory Builder, 2026-11-19). The workflow that runs it first is still to come.

    python3 -m harness.unasked

It writes `advice/advice-cost.json`, an `advice-cost/1` with no asks and no cost, into the new folder `advice`, from
what a Run knows before it has read anything: its id, the last word of its run-name, which the workflow hands it as
`NAME`; its attempt, as GitHub numbers it in `GITHUB_RUN_ATTEMPT`, since a re-run keeps its run's id; and its Release,
the one Release tag on the commit checked out (`steps.release`). It reads no key and nothing from GitHub. A Run that
stops before its advise step has then left a cost, nought, and a pass does not count the worst case for it;
`harness/advise.py` replaces the file before it asks anyone.

It needs the job's checkout to have fetched tags (`fetch-tags: true`): the Release is named from the checkout's own
tags, with no token, and a checkout with none has no Release this step can name.

The step never fails its job: with a run-name or an attempt it cannot read, no one Release tag on the checkout, tags
not fetched among the reasons, or a folder already there, it writes nothing and exits 0, and the pass counts the Run as
it counts any that left no cost. An attempt that cannot be read is never taken for the first, since a re-run would then
say that no reader was asked for an attempt that may have asked (the Factory Builder, 2026-11-28).
"""
from __future__ import annotations

import os
import re
import sys

from adapters import records
from harness import shared, steps

OUT = "advice"
COST = "advice-cost.json"
ATTEMPT = "GITHUB_RUN_ATTEMPT"
ATTEMPTS = 100      # the most attempts advice-cost/1 holds
NUMBER = re.compile(r"[1-9][0-9]{0,2}")       # ASCII digits alone, with no sign, space or leading nought


def attempt_of(environ: dict):
    """The Run's attempt, from `GITHUB_RUN_ATTEMPT`: a whole number from 1 to ATTEMPTS, or None where the environment
    gives none that can be read, and the caller then writes no cost."""
    said = environ.get(ATTEMPT)
    if isinstance(said, str) and NUMBER.fullmatch(said) and int(said) <= ATTEMPTS:
        return int(said)
    return None


def job(argv: list, environ: dict, base=None, release=steps.release) -> str:
    name, out = steps.given(argv, environ, ("NAME",), (OUT,))
    parts, attempt = records.named(name), attempt_of(environ)
    if parts is None:
        raise steps.Stop("run_name_unreadable")
    if attempt is None:
        raise steps.Stop("attempt_unreadable")
    document = {"schema": "advice-cost/1", "run": parts["run"], "attempt": attempt, "release": release(), "asks": 0,
                "cost_usd": 0}
    if shared.errors(document, "advice-cost"):
        raise steps.Stop("cost_unwritable")
    steps.write(steps.new_folder(os.getcwd() if base is None else base, out), COST, document)
    return "%s asks 0" % COST


def main(argv: list, env: dict) -> int:
    try:
        print(job(argv, env))
    except Exception as err:    # NOSONAR the step never fails its job: the Run goes on, and is counted as one that left no cost
        print("harness.unasked: %s" % type(err).__name__, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:], dict(os.environ)))
