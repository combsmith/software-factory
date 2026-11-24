"""The mutants of `release/fixtures/cut.v0-1-4.json`: tools/mutants.py runs them."""

from tools.mutants_of.common import NEXT_CUT_FIXTURE

TARGETS = ("release/fixtures/cut.v0-1-4.json",)
MUTANTS = [
    # The fifth cut's fixture, v0.1.4 at #714's merge: the same reads, `next` on again, and v0.1.3 left where it was.
    ('the fifth cut passed an eval of another workflow', 'release/fixtures/cut.v0-1-4.json',
     '\n              "path": ".github/workflows/eval.yml"', '\n              "path": ".github/workflows/ci.yml"',
     NEXT_CUT_FIXTURE),
    ('the fifth cut passed an eval that ended after it', 'release/fixtures/cut.v0-1-4.json',
     '\n              "updated_at": "2026-11-10T17:45:21Z"', '\n              "updated_at": "2026-11-10T17:48:21Z"',
     NEXT_CUT_FIXTURE),
    ('the fourth Release moved with the fifth cut', 'release/fixtures/cut.v0-1-4.json',
     '"ref": "refs/tags/factory/v0.1.3",\n              "object": {\n                "sha": "c2a5795dbac7f09aedc1fd6b89b685caff04f707"',
     '"ref": "refs/tags/factory/v0.1.3",\n              "object": {\n                "sha": "c1edc4a47c1bfbdf5e82b8229d5b4bea9c217e8f"',
     NEXT_CUT_FIXTURE),
    ("next's newest Deployment is not of the fifth Release", 'release/fixtures/cut.v0-1-4.json',
     '"description": "factory/v0.1.4"', '"description": "factory/v0.1.3"', NEXT_CUT_FIXTURE),
    ("the fifth cut's Deployment did not succeed", 'release/fixtures/cut.v0-1-4.json',
     '"id": 21878970444,\n                "state": "success"', '"id": 21878970444,\n                "state": "failure"',
     NEXT_CUT_FIXTURE),
    ("the fourth Release's Deployment still reads its success", 'release/fixtures/cut.v0-1-4.json',
     '"state": "inactive"', '"state": "success"', NEXT_CUT_FIXTURE),
    ('the fifth cut passed another eval run', 'release/fixtures/cut.v0-1-4.json',
     '\n              "id": 42865325326,', '\n              "id": 42865325327,', NEXT_CUT_FIXTURE),
    ('the fifth cut passed an eval of another commit', 'release/fixtures/cut.v0-1-4.json',
     '"head_sha": "c1edc4a47c1bfbdf5e82b8229d5b4bea9c217e8f",\n              "run_attempt": 1,\n              "workflow_id": 399025209',
     '"head_sha": "c2a5795dbac7f09aedc1fd6b89b685caff04f707",\n              "run_attempt": 1,\n              "workflow_id": 399025209',
     NEXT_CUT_FIXTURE),
    ('the eval workflow ran another run on the fifth cut commit', 'release/fixtures/cut.v0-1-4.json',
     '\n                  "id": 42865325326,', '\n                  "id": 42865325327,', NEXT_CUT_FIXTURE),
]
