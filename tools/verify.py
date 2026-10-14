"""One command: everything the required check will run. `make verify`."""
from __future__ import annotations

import sys
import unittest

from tools import (check_apps, check_authority, check_context, check_examples, check_lifecycle, check_purity,
                   check_repo, check_workflows)

CHECKS = [
    ("schemas and examples", check_examples.run),
    ("lifecycle", check_lifecycle.run),
    ("authority", check_authority.run),
    ("apps", check_apps.run),
    ("kernel purity", check_purity.run),
    ("repo", check_repo.run),
    ("workflows", check_workflows.run),
    ("context", check_context.run),
]


def failed(checks: list) -> bool:
    """Run each check, print what it found, and say whether any found a problem."""
    any_failed = False
    for name, check in checks:
        problems = check()
        print("%-22s %s" % (name, "ok" if not problems else "FAILED"))
        for p in problems:
            print("    " + p)
        any_failed = any_failed or bool(problems)
    return any_failed


def main() -> int:
    checks_failed = failed(CHECKS)
    suite = unittest.defaultTestLoader.discover("tests")
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return 1 if checks_failed or not result.wasSuccessful() else 0


if __name__ == "__main__":
    sys.exit(main())
