"""The mutants of `.github/workflows/eval.yml`: tools/mutants.py runs them."""

from tools.mutants_of.common import NEEDED

TARGETS = (".github/workflows/eval.yml",)
MUTANTS = [
    # Issue 388: each run: step stops under a limit of its own, the steps together below their job's.
    ("the eval job's run step is cut before its budget", ".github/workflows/eval.yml",
     "        timeout-minutes: 109\n", "        timeout-minutes: 30\n", NEEDED),
]
