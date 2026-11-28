"""The mutants of `tools/rulesets_drift.sh`: tools/mutants.py runs them."""

TARGETS = ("tools/rulesets_drift.sh",)
from tools.mutants_of.common import ISOLATED, ISOLATED_TEST, UNISOLATED, WITH_SITE  # noqa: E402
MUTANTS = [
    # The record of `main` after issue 198's switch (decision 0191): each field back, and the four together, which
    # `tools/check_rulesets.py` lets through as a `main` that counts no approval.
    ("a scratch directory reached through a link may be inside the repo", "tools/rulesets_drift.sh",
     'real=$(cd "$dir" && pwd -P)\n', 'real=$dir\n',
     ("tests.test_tools.RulesetsDrift.test_a_scratch_directory_inside_the_repo_is_refused_however_it_is_reached",)),
    # Issue 1300: its redaction runs as a file under -I.
    ("rulesets_drift.sh runs a redaction the shell's modules can steer", "tools/rulesets_drift.sh", ISOLATED + ' < "$dir/raw"', UNISOLATED + ' < "$dir/raw"',
     ISOLATED_TEST),
    ("rulesets_drift.sh runs a redaction that reads site-packages", "tools/rulesets_drift.sh", ISOLATED + ' < "$dir/raw"', WITH_SITE + ' < "$dir/raw"',
     ISOLATED_TEST),
]
