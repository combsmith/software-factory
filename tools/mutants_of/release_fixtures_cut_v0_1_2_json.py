"""The mutants of `release/fixtures/cut.v0-1-2.json`: tools/mutants.py runs them."""

from tools.mutants_of.common import NEXT_CUT_FIXTURE

TARGETS = ("release/fixtures/cut.v0-1-2.json",)
MUTANTS = [
    # The third cut's fixture, v0.1.2 at #694's merge: the same reads, `next` on again, and v0.1.1 left where it was.
    ('the third cut passed an eval of another workflow', 'release/fixtures/cut.v0-1-2.json',
     '\n              "path": ".github/workflows/eval.yml"', '\n              "path": ".github/workflows/ci.yml"',
     NEXT_CUT_FIXTURE),
    ('the third cut passed an eval that ended after it', 'release/fixtures/cut.v0-1-2.json',
     '\n              "updated_at": "2026-11-10T02:16:08Z"', '\n              "updated_at": "2026-11-10T02:18:08Z"',
     NEXT_CUT_FIXTURE),
    ('the second Release moved with the third cut', 'release/fixtures/cut.v0-1-2.json',
     '"ref": "refs/tags/factory/v0.1.1",\n              "object": {\n                "sha": "7ff090d7d59e3ef6c32b3ae957d9f2cc6fb3000a"',
     '"ref": "refs/tags/factory/v0.1.1",\n              "object": {\n                "sha": "d960dc5828572b2289a9718f28ff2d6cb081a2e7"',
     NEXT_CUT_FIXTURE),
    ("next's newest Deployment is not of the third Release", 'release/fixtures/cut.v0-1-2.json',
     '"description": "factory/v0.1.2"', '"description": "factory/v0.1.1"', NEXT_CUT_FIXTURE),
    ("the third cut's Deployment did not succeed", 'release/fixtures/cut.v0-1-2.json',
     '"id": 21816439642,\n                "state": "success"', '"id": 21816439642,\n                "state": "failure"',
     NEXT_CUT_FIXTURE),
    ("the second Release's Deployment still reads its success", 'release/fixtures/cut.v0-1-2.json',
     '"state": "inactive"', '"state": "success"', NEXT_CUT_FIXTURE),
    ('the third cut passed another eval run', 'release/fixtures/cut.v0-1-2.json',
     '\n              "id": 42739717534,', '\n              "id": 42739717535,', NEXT_CUT_FIXTURE),
    ('the third cut passed an eval of another commit', 'release/fixtures/cut.v0-1-2.json',
     '"head_sha": "d960dc5828572b2289a9718f28ff2d6cb081a2e7",\n              "run_attempt": 1,\n              "workflow_id": 399025209',
     '"head_sha": "7ff090d7d59e3ef6c32b3ae957d9f2cc6fb3000a",\n              "run_attempt": 1,\n              "workflow_id": 399025209',
     NEXT_CUT_FIXTURE),
    ('the eval workflow ran another run on the third cut commit', 'release/fixtures/cut.v0-1-2.json',
     '\n                  "id": 42739717534,', '\n                  "id": 42739717535,', NEXT_CUT_FIXTURE),
]
