"""The required check's verdict on the jobs it needs: it passes only when every one of them passed.

`verify` needs every other job in its workflow and runs under `if: always()`, so it reports when one
of them fails, is skipped or is cancelled: with a plain `needs:` it would be skipped then, and GitHub
passes a required check that is skipped. This is what fails it. GitHub gives the jobs' results as
JSON in `NEEDS`, from `${{ toJSON(needs) }}`. It passes only when that can be read, names at least one
job, and every job's `result` is exactly `success`. Run with `python3 -m tools.needs_passed`.
"""
from __future__ import annotations

import json
import os
import sys


def problems(text) -> list:
    """Why the jobs `text` describes, the JSON of `needs`, did not all pass: nothing when every one did."""
    try:
        needs = json.loads(text)
    except (TypeError, ValueError):
        return ["NEEDS cannot be read as JSON; give it ${{ toJSON(needs) }} in the job's env"]
    if not isinstance(needs, dict) or not needs:
        return ["NEEDS names no job; the required check must need every other job in its workflow"]
    found = []
    for job, said in sorted(needs.items()):
        result = said.get("result") if isinstance(said, dict) else None
        if result != "success":
            found.append("the job %s ended %s, and only success passes" % (job, json.dumps(result)))
    return found


def main(environ=os.environ) -> int:
    found = problems(environ.get("NEEDS"))
    for problem in found:
        print(problem)
    if not found:
        print("every job the required check needs passed: %s" % ", ".join(sorted(json.loads(environ["NEEDS"]))))
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
