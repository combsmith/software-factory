"""The mutants of `release/fixtures/cut.v0-1-6.json`: tools/mutants.py runs them."""

from tools.mutants_of.common import NEXT_CUT_FIXTURE

TARGETS = ("release/fixtures/cut.v0-1-6.json",)
MUTANTS = [
    # The seventh cut's fixture, v0.1.6 at #717's merge: the same reads, `next` on again, and v0.1.5 left where it was.
    ('the seventh cut passed an eval of another workflow', 'release/fixtures/cut.v0-1-6.json',
     '\n              "path": ".github/workflows/eval.yml"', '\n              "path": ".github/workflows/ci.yml"',
     NEXT_CUT_FIXTURE),
    ('the seventh cut passed an eval that ended after it', 'release/fixtures/cut.v0-1-6.json',
     '\n              "updated_at": "2026-11-10T23:43:42Z"', '\n              "updated_at": "2026-11-10T23:46:42Z"',
     NEXT_CUT_FIXTURE),
    ('the sixth Release moved with the seventh cut', 'release/fixtures/cut.v0-1-6.json',
     '"ref": "refs/tags/factory/v0.1.5",\n              "object": {\n                "sha": "26d6c67eab11023366515196f4c83ad31f36a364"',
     '"ref": "refs/tags/factory/v0.1.5",\n              "object": {\n                "sha": "48687f2a79b6f4091326a0fa88556d5795e8478a"',
     NEXT_CUT_FIXTURE),
    ("next's newest Deployment is not of the seventh Release", 'release/fixtures/cut.v0-1-6.json',
     '"description": "factory/v0.1.6"', '"description": "factory/v0.1.5"', NEXT_CUT_FIXTURE),
    ("the seventh cut's Deployment did not succeed", 'release/fixtures/cut.v0-1-6.json',
     '"id": 21903713521,\n                "state": "success"', '"id": 21903713521,\n                "state": "failure"',
     NEXT_CUT_FIXTURE),
    ("the sixth Release's Deployment still reads its success", 'release/fixtures/cut.v0-1-6.json',
     '"state": "inactive"', '"state": "success"', NEXT_CUT_FIXTURE),
    ('the seventh cut passed another eval run', 'release/fixtures/cut.v0-1-6.json',
     '\n              "id": 42923463050,', '\n              "id": 42923463051,', NEXT_CUT_FIXTURE),
    ('the seventh cut passed an eval of another commit', 'release/fixtures/cut.v0-1-6.json',
     '"head_sha": "48687f2a79b6f4091326a0fa88556d5795e8478a",\n              "run_attempt": 1,\n              "workflow_id": 399025209',
     '"head_sha": "26d6c67eab11023366515196f4c83ad31f36a364",\n              "run_attempt": 1,\n              "workflow_id": 399025209',
     NEXT_CUT_FIXTURE),
    ('the eval workflow ran another run on the seventh cut commit', 'release/fixtures/cut.v0-1-6.json',
     '\n                  "id": 42923463050,', '\n                  "id": 42923463051,', NEXT_CUT_FIXTURE),
]
