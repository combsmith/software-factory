"""The mutants of `release/fixtures/cut.v0-1-3.json`: tools/mutants.py runs them."""

from tools.mutants_of.common import NEXT_CUT_FIXTURE

TARGETS = ("release/fixtures/cut.v0-1-3.json",)
MUTANTS = [
    # The fourth cut's fixture, v0.1.3 at #708's merge: the same reads, `next` on again, and v0.1.2 left where it was.
    ('the fourth cut passed an eval of another workflow', 'release/fixtures/cut.v0-1-3.json',
     '\n              "path": ".github/workflows/eval.yml"', '\n              "path": ".github/workflows/ci.yml"',
     NEXT_CUT_FIXTURE),
    ('the fourth cut passed an eval that ended after it', 'release/fixtures/cut.v0-1-3.json',
     '\n              "updated_at": "2026-11-10T04:21:30Z"', '\n              "updated_at": "2026-11-10T04:23:30Z"',
     NEXT_CUT_FIXTURE),
    ('the third Release moved with the fourth cut', 'release/fixtures/cut.v0-1-3.json',
     '"ref": "refs/tags/factory/v0.1.2",\n              "object": {\n                "sha": "d960dc5828572b2289a9718f28ff2d6cb081a2e7"',
     '"ref": "refs/tags/factory/v0.1.2",\n              "object": {\n                "sha": "c2a5795dbac7f09aedc1fd6b89b685caff04f707"',
     NEXT_CUT_FIXTURE),
    ("next's newest Deployment is not of the fourth Release", 'release/fixtures/cut.v0-1-3.json',
     '"description": "factory/v0.1.3"', '"description": "factory/v0.1.2"', NEXT_CUT_FIXTURE),
    ("the fourth cut's Deployment did not succeed", 'release/fixtures/cut.v0-1-3.json',
     '"id": 21822781018,\n                "state": "success"', '"id": 21822781018,\n                "state": "failure"',
     NEXT_CUT_FIXTURE),
    ("the third Release's Deployment still reads its success", 'release/fixtures/cut.v0-1-3.json',
     '"state": "inactive"', '"state": "success"', NEXT_CUT_FIXTURE),
    ('the fourth cut passed another eval run', 'release/fixtures/cut.v0-1-3.json',
     '\n              "id": 42753588971,', '\n              "id": 42753588972,', NEXT_CUT_FIXTURE),
    ('the fourth cut passed an eval of another commit', 'release/fixtures/cut.v0-1-3.json',
     '"head_sha": "c2a5795dbac7f09aedc1fd6b89b685caff04f707",\n              "run_attempt": 1,\n              "workflow_id": 399025209',
     '"head_sha": "d960dc5828572b2289a9718f28ff2d6cb081a2e7",\n              "run_attempt": 1,\n              "workflow_id": 399025209',
     NEXT_CUT_FIXTURE),
    ('the eval workflow ran another run on the fourth cut commit', 'release/fixtures/cut.v0-1-3.json',
     '\n                  "id": 42753588971,', '\n                  "id": 42753588972,', NEXT_CUT_FIXTURE),
]
