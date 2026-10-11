"""One command: everything the required check will run. `make verify`."""
from __future__ import annotations

import sys
import unittest

from tools import check_authority, check_examples, check_lifecycle, check_purity

CHECKS = [
    ("schemas and examples", check_examples.run),
    ("lifecycle", check_lifecycle.run),
    ("authority", check_authority.run),
    ("kernel purity", check_purity.run),
]


def main() -> int:
    failed = False
    for name, check in CHECKS:
        problems = check()
        print("%-22s %s" % (name, "ok" if not problems else "FAILED"))
        for p in problems:
            print("    " + p)
        failed = failed or bool(problems)
    suite = unittest.defaultTestLoader.discover("tests")
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return 1 if failed or not result.wasSuccessful() else 0


if __name__ == "__main__":
    sys.exit(main())
