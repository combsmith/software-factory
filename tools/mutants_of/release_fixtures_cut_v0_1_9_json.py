"""The mutants of `release/fixtures/cut.v0-1-9.json`: tools/mutants.py runs them."""

from tools.mutants_of.common import NEXT_CUT_FIXTURE

TARGETS = ("release/fixtures/cut.v0-1-9.json",)
MUTANTS = [
    # The tenth cut's fixture, v0.1.9 at #775's merge: the same reads, `next` on again, and v0.1.8 left where it was.
    ('the tenth cut passed an eval of another workflow', 'release/fixtures/cut.v0-1-9.json',
     '\n              "path": ".github/workflows/eval.yml"',
     '\n              "path": ".github/workflows/ci.yml"',
     NEXT_CUT_FIXTURE),
    ('the tenth cut passed an eval that ended after it', 'release/fixtures/cut.v0-1-9.json',
     '\n              "updated_at": "2026-11-12T07:13:28Z"',
     '\n              "updated_at": "2026-11-12T07:16:28Z"',
     NEXT_CUT_FIXTURE),
    ('the ninth Release moved with the tenth cut', 'release/fixtures/cut.v0-1-9.json',
     '"ref": "refs/tags/factory/v0.1.8",\n              "object": {\n                "sha": "caa396523330ee0cc35ccb0bd42fbe1efa5c25aa"',
     '"ref": "refs/tags/factory/v0.1.8",\n              "object": {\n                "sha": "b61f0ecb0a44d77f77e06aca4c72896c633e83df"',
     NEXT_CUT_FIXTURE),
    ("next's newest Deployment is not of the tenth Release", 'release/fixtures/cut.v0-1-9.json',
     '"description": "factory/v0.1.9"',
     '"description": "factory/v0.1.8"',
     NEXT_CUT_FIXTURE),
    ("the tenth cut's Deployment did not succeed", 'release/fixtures/cut.v0-1-9.json',
     '"id": 22011469540,\n                "state": "success"',
     '"id": 22011469540,\n                "state": "failure"',
     NEXT_CUT_FIXTURE),
    ("the ninth Release's Deployment still reads its success", 'release/fixtures/cut.v0-1-9.json',
     '"state": "inactive"',
     '"state": "success"',
     NEXT_CUT_FIXTURE),
    ('the tenth cut passed another eval run', 'release/fixtures/cut.v0-1-9.json',
     '\n              "id": 43171810453,',
     '\n              "id": 43171810454,',
     NEXT_CUT_FIXTURE),
    ('the tenth cut passed an eval of another commit', 'release/fixtures/cut.v0-1-9.json',
     '"head_sha": "b61f0ecb0a44d77f77e06aca4c72896c633e83df",\n              "run_attempt": 1,\n              "workflow_id": 399025209',
     '"head_sha": "caa396523330ee0cc35ccb0bd42fbe1efa5c25aa",\n              "run_attempt": 1,\n              "workflow_id": 399025209',
     NEXT_CUT_FIXTURE),
    ('the eval workflow ran another run on the tenth cut commit', 'release/fixtures/cut.v0-1-9.json',
     '\n                  "id": 43171810453,',
     '\n                  "id": 43171810454,',
     NEXT_CUT_FIXTURE),
]
