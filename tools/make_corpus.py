"""Record every decision the Python Kernel makes, for another implementation to replay.

Writes corpus/decisions.jsonl: one line per call, with the inputs and the
expected Decision in canonical JSON. Sources: the seeded simulator, with its
faults, and every case in tests/test_decide.py.
"""
from __future__ import annotations

import json
import pathlib
import sys
import unittest

import kernel.decide
import sim.world
import tests.test_decide

ROOT = pathlib.Path(__file__).resolve().parent.parent
real = kernel.decide.decide
seen, lines = set(), []


def canon(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def recording(facts, runs, context, config, now):
    result = real(facts, runs, context, config, now)
    line = canon({"facts": facts, "runs": runs, "context": context, "config": config, "now": now,
                  "expected": canon(result)})
    if line not in seen:
        seen.add(line)
        lines.append(line)
    return result


def main(seeds: int = 150) -> int:
    sim.world.decide = recording
    tests.test_decide.decide = recording
    for seed in range(1, seeds + 1):
        world = sim.world.World(seed)
        for _ in range(150):
            world.step()
        world.settle()
    unittest.TextTestRunner(verbosity=0).run(unittest.defaultTestLoader.loadTestsFromModule(tests.test_decide))
    out = ROOT / "corpus" / "decisions.jsonl"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n")
    print("%d distinct decisions written to %s" % (len(lines), out.relative_to(ROOT)))
    return 0


if __name__ == "__main__":
    sys.exit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 150))
