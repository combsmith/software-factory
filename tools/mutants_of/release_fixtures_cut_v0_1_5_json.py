"""The mutants of `release/fixtures/cut.v0-1-5.json`: tools/mutants.py runs them."""

from tools.mutants_of.common import NEXT_CUT_FIXTURE

TARGETS = ("release/fixtures/cut.v0-1-5.json",)
MUTANTS = [
    # The sixth cut's fixture, v0.1.5 at #720's merge: the same reads, `next` on again, and v0.1.4 left where it was.
    ('the sixth cut passed an eval of another workflow', 'release/fixtures/cut.v0-1-5.json',
     '\n              "path": ".github/workflows/eval.yml"', '\n              "path": ".github/workflows/ci.yml"',
     NEXT_CUT_FIXTURE),
    ('the sixth cut passed an eval that ended after it', 'release/fixtures/cut.v0-1-5.json',
     '\n              "updated_at": "2026-11-10T19:23:47Z"', '\n              "updated_at": "2026-11-10T19:26:47Z"',
     NEXT_CUT_FIXTURE),
    ('the fifth Release moved with the sixth cut', 'release/fixtures/cut.v0-1-5.json',
     '"ref": "refs/tags/factory/v0.1.4",\n              "object": {\n                "sha": "c1edc4a47c1bfbdf5e82b8229d5b4bea9c217e8f"',
     '"ref": "refs/tags/factory/v0.1.4",\n              "object": {\n                "sha": "26d6c67eab11023366515196f4c83ad31f36a364"',
     NEXT_CUT_FIXTURE),
    ("next's newest Deployment is not of the sixth Release", 'release/fixtures/cut.v0-1-5.json',
     '"description": "factory/v0.1.5"', '"description": "factory/v0.1.4"', NEXT_CUT_FIXTURE),
    ("the sixth cut's Deployment did not succeed", 'release/fixtures/cut.v0-1-5.json',
     '"id": 21886041183,\n                "state": "success"', '"id": 21886041183,\n                "state": "failure"',
     NEXT_CUT_FIXTURE),
    ("the fifth Release's Deployment still reads its success", 'release/fixtures/cut.v0-1-5.json',
     '"state": "inactive"', '"state": "success"', NEXT_CUT_FIXTURE),
    ('the sixth cut passed another eval run', 'release/fixtures/cut.v0-1-5.json',
     '\n              "id": 42882105104,', '\n              "id": 42882105105,', NEXT_CUT_FIXTURE),
    ('the sixth cut passed an eval of another commit', 'release/fixtures/cut.v0-1-5.json',
     '"head_sha": "26d6c67eab11023366515196f4c83ad31f36a364",\n              "run_attempt": 1,\n              "workflow_id": 399025209',
     '"head_sha": "c1edc4a47c1bfbdf5e82b8229d5b4bea9c217e8f",\n              "run_attempt": 1,\n              "workflow_id": 399025209',
     NEXT_CUT_FIXTURE),
    ('the eval workflow ran another run on the sixth cut commit', 'release/fixtures/cut.v0-1-5.json',
     '\n                  "id": 42882105104,', '\n                  "id": 42882105105,', NEXT_CUT_FIXTURE),
]
