"""The mutants of `release/fixtures/cut.v0-1-1.json`: tools/mutants.py runs them."""

from tools.mutants_of.common import NEXT_CUT_FIXTURE

TARGETS = ("release/fixtures/cut.v0-1-1.json",)
MUTANTS = [
    # The first cut's fixture: the ruleset that keeps a Release tag immutable, read after the cut (records 0071, 0120).
    # The second cut's fixture: the eval it passed, `next` moved on, and the first Release left where it was.
    ('the second cut passed an eval of another workflow', 'release/fixtures/cut.v0-1-1.json',
     '\n              "path": ".github/workflows/eval.yml"', '\n              "path": ".github/workflows/ci.yml"',
     NEXT_CUT_FIXTURE),
    ('the second cut passed an eval that ended after it', 'release/fixtures/cut.v0-1-1.json',
     '\n              "updated_at": "2026-11-09T20:52:53Z"', '\n              "updated_at": "2026-11-09T20:55:53Z"',
     NEXT_CUT_FIXTURE),
    ('the first Release moved with the second cut', 'release/fixtures/cut.v0-1-1.json',
     '"ref": "refs/tags/factory/v0.1.0",\n              "object": {\n                "sha": "499835d5384ba81c466b17199edcde1848431630"',
     '"ref": "refs/tags/factory/v0.1.0",\n              "object": {\n                "sha": "7ff090d7d59e3ef6c32b3ae957d9f2cc6fb3000a"',
     NEXT_CUT_FIXTURE),
    ("next's newest Deployment is not of the second Release", 'release/fixtures/cut.v0-1-1.json',
     '"description": "factory/v0.1.1"', '"description": "factory/v0.1.0"', NEXT_CUT_FIXTURE),
    ("the second cut's Deployment did not succeed", 'release/fixtures/cut.v0-1-1.json',
     '"id": 21798083435,\n                "state": "success"', '"id": 21798083435,\n                "state": "failure"',
     NEXT_CUT_FIXTURE),
    ("the first Release's Deployment still reads its success", 'release/fixtures/cut.v0-1-1.json',
     '"state": "inactive"', '"state": "success"', NEXT_CUT_FIXTURE),
    ('the second cut passed another eval run', 'release/fixtures/cut.v0-1-1.json',
     '\n              "id": 42694638100,', '\n              "id": 42694638101,', NEXT_CUT_FIXTURE),
    ('the second cut passed an eval of another commit', 'release/fixtures/cut.v0-1-1.json',
     '"head_sha": "7ff090d7d59e3ef6c32b3ae957d9f2cc6fb3000a",\n              "run_attempt": 1,\n              "workflow_id": 399025209',
     '"head_sha": "499835d5384ba81c466b17199edcde1848431630",\n              "run_attempt": 1,\n              "workflow_id": 399025209',
     NEXT_CUT_FIXTURE),
    ('the eval workflow ran another run on the cut commit', 'release/fixtures/cut.v0-1-1.json',
     '\n                  "id": 42694638100,', '\n                  "id": 42694638101,', NEXT_CUT_FIXTURE),
]
