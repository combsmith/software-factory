"""`python3 -m release.move plan < READS`: the plan of one step, from what was read (rulings 4′ and 5′).

READS, on standard input, is one JSON object: `step`, the step asked (`release/cut.py`'s), `refs`, the refs
`adapters/tags.py` read, and `facts`, the facts of the commit asked about. It opens no path it is given (SonarCloud's
S2083 and S8707), as `tools/redact_trial.py` opens none. The Channels a step may move are those `release/rings.json`
declares. It prints `{"writes": [...]}` and exits 0, or `{"refused": code}` and exits 1, and writes nothing. Reads
that cannot be read are refused, `step_unreadable`. The run that sends the writes, reads each back and records the
Deployment is the release workflow's, a later pull request's.
"""
from __future__ import annotations

import json
import pathlib
import sys

from release import cut

RINGS = pathlib.Path(__file__).resolve().parent / "rings.json"
USAGE = "usage: python3 -m release.move plan < READS"


def _rings(path: pathlib.Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def channels(rings) -> frozenset:
    """The Channels the ring file declares, by tag; none when it cannot be read."""
    found = rings.get("channels") if isinstance(rings, dict) else None
    if not isinstance(found, dict) or not all(isinstance(c, dict) for c in found.values()):
        return frozenset()
    return frozenset(c.get("tag") for c in found.values())


def main(argv, stdin=None, rings=RINGS) -> int:
    if list(argv) != ["plan"]:
        print(USAGE, file=sys.stderr)
        return 2
    try:
        reads = json.loads((sys.stdin if stdin is None else stdin).read())
    except ValueError:
        reads = None
    reads = reads if isinstance(reads, dict) else {}
    writes, refused = cut.plan(reads.get("step"), reads.get("refs"), reads.get("facts"), channels(_rings(rings)))
    if refused:
        print(json.dumps({"refused": refused}))
        return 1
    print(json.dumps({"writes": [list(write) for write in writes]}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
