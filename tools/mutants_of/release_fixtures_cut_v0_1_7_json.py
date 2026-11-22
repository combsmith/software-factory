"""The mutants of `release/fixtures/cut.v0-1-7.json`: tools/mutants.py runs them."""

from tools.mutants_of.common import NEXT_CUT_FIXTURE

TARGETS = ("release/fixtures/cut.v0-1-7.json",)
MUTANTS = [
    # The eighth cut's fixture, v0.1.7 at #731's merge: the same reads, `next` on again, and v0.1.6 left where it was.
    ('the eighth cut passed an eval of another workflow', 'release/fixtures/cut.v0-1-7.json',
     '\n              "path": ".github/workflows/eval.yml"',
     '\n              "path": ".github/workflows/ci.yml"',
     NEXT_CUT_FIXTURE),
    ('the eighth cut passed an eval that ended after it', 'release/fixtures/cut.v0-1-7.json',
     '\n              "updated_at": "2026-11-11T13:09:17Z"',
     '\n              "updated_at": "2026-11-11T13:12:17Z"',
     NEXT_CUT_FIXTURE),
    ('the seventh Release moved with the eighth cut', 'release/fixtures/cut.v0-1-7.json',
     '"ref": "refs/tags/factory/v0.1.6",\n              "object": {\n                "sha": "48687f2a79b6f4091326a0fa88556d5795e8478a"',
     '"ref": "refs/tags/factory/v0.1.6",\n              "object": {\n                "sha": "68efced8fd78641a239a6e5f41e0c81db6619684"',
     NEXT_CUT_FIXTURE),
    ("next's newest Deployment is not of the eighth Release", 'release/fixtures/cut.v0-1-7.json',
     '"description": "factory/v0.1.7"',
     '"description": "factory/v0.1.6"',
     NEXT_CUT_FIXTURE),
    ("the eighth cut's Deployment did not succeed", 'release/fixtures/cut.v0-1-7.json',
     '"id": 21947830800,\n                "state": "success"',
     '"id": 21947830800,\n                "state": "failure"',
     NEXT_CUT_FIXTURE),
    ("the seventh Release's Deployment still reads its success", 'release/fixtures/cut.v0-1-7.json',
     '"state": "inactive"',
     '"state": "success"',
     NEXT_CUT_FIXTURE),
    ('the eighth cut passed another eval run', 'release/fixtures/cut.v0-1-7.json',
     '\n              "id": 43024260112,',
     '\n              "id": 43024260113,',
     NEXT_CUT_FIXTURE),
    ('the eighth cut passed an eval of another commit', 'release/fixtures/cut.v0-1-7.json',
     '"head_sha": "68efced8fd78641a239a6e5f41e0c81db6619684",\n              "run_attempt": 1,\n              "workflow_id": 399025209',
     '"head_sha": "48687f2a79b6f4091326a0fa88556d5795e8478a",\n              "run_attempt": 1,\n              "workflow_id": 399025209',
     NEXT_CUT_FIXTURE),
    ('the eval workflow ran another run on the eighth cut commit', 'release/fixtures/cut.v0-1-7.json',
     '\n                  "id": 43024260112,',
     '\n                  "id": 43024260113,',
     NEXT_CUT_FIXTURE),
]
