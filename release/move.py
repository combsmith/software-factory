"""`python3 -m release.move plan STEP REFS FACTS`: the plan of one step, from what was read (rulings 4′ and 5′).

Each argument is a JSON file: the step asked (`release/cut.py`'s), the refs `adapters/tags.py` read, and the facts of
the commit asked about. It prints `{"writes": [...]}` and exits 0, or `{"refused": code}` and exits 1, and writes
nothing. A file it cannot read is refused, `step_unreadable`. The run that sends the writes, reads each back and
records the Deployment is `release.yml`'s, the next pull request's.
"""
from __future__ import annotations

import json
import sys

from release import cut

USAGE = "usage: python3 -m release.move plan STEP REFS FACTS"


def _read(path: str):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def main(argv) -> int:
    if len(argv) != 4 or argv[0] != "plan":
        print(USAGE, file=sys.stderr)
        return 2
    step, refs, facts = (_read(path) for path in argv[1:])
    writes, refused = cut.plan(step, refs, facts)
    if refused:
        print(json.dumps({"refused": refused}))
        return 1
    print(json.dumps({"writes": [list(write) for write in writes]}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
