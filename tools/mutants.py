"""Can the tests fail? Break the Kernel on purpose, one rule at a time, and see.

Each mutant removes or inverts one rule. A mutant that the tests do not catch
is a rule nothing is checking. Run with `python3 -m tools.mutants`.
"""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
MUTANTS = [
    ("incomplete facts are trusted", "kernel/derive.py",
     "    gaps = incomplete(facts)\n", "    gaps = []\n"),
    ("model review before the checks pass", "kernel/derive.py",
     "    if waiting:\n", "    if False:\n"),
    ("a failed check is ignored", "kernel/derive.py",
     "    if failed:\n", "    if False:\n"),
    ("a stranger's thread gates", "kernel/derive.py",
     'if by["kind"] == "human" and by["can_write"]:', 'if by["kind"] == "human":'),
    ("a minor finding gates", "kernel/derive.py",
     'th["severity"] in t.GATING_SEVERITIES', "True"),
    ("an empty diff converges", "kernel/derive.py",
     'if facts["diff"]["files"] == 0:', "if False:"),
    ("admission survives a push", "kernel/derive.py",
     'return facts["admitted_at"] > facts["last_push_at"]', "return True"),
    ("an approval of other content stands", "kernel/derive.py",
     'and rv["content_id"] == facts["content_id"]\n        ):', "):"),
    ("a review of other content counts", "kernel/derive.py",
     '        and r["content_id"] == facts["content_id"]\n        and r["status"] == "completed"',
     '        and r["status"] == "completed"'),
    ("the hold label is ignored", "kernel/derive.py",
     "    if t.LABEL_HOLD in labels:\n", "    if False:\n"),
    ("two Runs on one item", "kernel/decide.py",
     "    if in_progress(mine):\n", "    if False:\n"),
    ("the approver may be the author", "kernel/decide.py",
     'if config["approver"] in (facts["author"], facts["last_pusher"]):', "if False:"),
    ("the pause is ignored", "kernel/decide.py",
     '    if context.get("paused") is not False:\n', "    if False:\n"),
    ("attempts are unlimited", "kernel/decide.py",
     '    if len(attempts) >= limits["max_attempts"]:\n', "    if False:\n"),
    ("capacity faults count as attempts", "kernel/decide.py",
     ' and r.get("outcome") == "item"]', "]"),
    ("rounds are unlimited", "kernel/decide.py",
     '        if len(rounds) >= limits["max_rounds"]:\n', "        if False:\n"),
    ("the run ceiling is ignored", "kernel/decide.py",
     '    if len(recent) >= limits["max_runs_per_item"]:\n', "    if False:\n"),
    ("a capacity fault does not defer", "kernel/decide.py",
     "    if until is not None and until > now:\n", "    if False:\n"),
    ("the org limit is ignored", "kernel/decide.py",
     '    if active >= limits["org_max_active_runs"]:\n', "    if False:\n"),
]


def main() -> int:
    survived = []
    env = dict(os.environ, SIM_SEEDS="40", MUTATING="1")
    whole = subprocess.run([sys.executable, "-m", "unittest", "discover", "-q", "tests"],
                           cwd=ROOT, env=env, capture_output=True)
    if whole.returncode != 0:
        print("the tests fail before anything is broken; a mutant cannot be told from that")
        return 1
    for name, rel, old, new in MUTANTS:
        with tempfile.TemporaryDirectory() as tmp:
            work = pathlib.Path(tmp) / "repo"
            shutil.copytree(ROOT, work, ignore=shutil.ignore_patterns(".git", "__pycache__"))
            target = work / rel
            text = target.read_text()
            if text.count(old) != 1:
                print("STALE     %s (the code it mutates has changed)" % name)
                survived.append(name)
                continue
            target.write_text(text.replace(old, new))
            done = subprocess.run([sys.executable, "-m", "unittest", "discover", "-q", "tests"],
                                  cwd=work, env=env, capture_output=True)
            killed = done.returncode != 0
            print("%-9s %s" % ("killed" if killed else "SURVIVED", name))
            if not killed:
                survived.append(name)
    print("%d of %d mutants killed" % (len(MUTANTS) - len(survived), len(MUTANTS)))
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main())
