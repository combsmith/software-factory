"""The mutants of `release/fixtures/cut.v0-1-8.json`: tools/mutants.py runs them."""

from tools.mutants_of.common import NEXT_CUT_FIXTURE

TARGETS = ("release/fixtures/cut.v0-1-8.json",)
MUTANTS = [
    # The ninth cut's fixture, v0.1.8 at #748's merge: the same reads, `next` on again, and v0.1.7 left where it was.
    ('the ninth cut passed an eval of another workflow', 'release/fixtures/cut.v0-1-8.json',
     '\n              "path": ".github/workflows/eval.yml"',
     '\n              "path": ".github/workflows/ci.yml"',
     NEXT_CUT_FIXTURE),
    ('the ninth cut passed an eval that ended after it', 'release/fixtures/cut.v0-1-8.json',
     '\n              "updated_at": "2026-11-11T22:17:05Z"',
     '\n              "updated_at": "2026-11-11T22:20:05Z"',
     NEXT_CUT_FIXTURE),
    ('the eighth Release moved with the ninth cut', 'release/fixtures/cut.v0-1-8.json',
     '"ref": "refs/tags/factory/v0.1.7",\n              "object": {\n                "sha": "68efced8fd78641a239a6e5f41e0c81db6619684"',
     '"ref": "refs/tags/factory/v0.1.7",\n              "object": {\n                "sha": "caa396523330ee0cc35ccb0bd42fbe1efa5c25aa"',
     NEXT_CUT_FIXTURE),
    ("next's newest Deployment is not of the ninth Release", 'release/fixtures/cut.v0-1-8.json',
     '"description": "factory/v0.1.8"',
     '"description": "factory/v0.1.7"',
     NEXT_CUT_FIXTURE),
    ("the ninth cut's Deployment did not succeed", 'release/fixtures/cut.v0-1-8.json',
     '"id": 21984638691,\n                "state": "success"',
     '"id": 21984638691,\n                "state": "failure"',
     NEXT_CUT_FIXTURE),
    ("the eighth Release's Deployment still reads its success", 'release/fixtures/cut.v0-1-8.json',
     '"state": "inactive"',
     '"state": "success"',
     NEXT_CUT_FIXTURE),
    ('the ninth cut passed another eval run', 'release/fixtures/cut.v0-1-8.json',
     '\n              "id": 43107717326,',
     '\n              "id": 43107717327,',
     NEXT_CUT_FIXTURE),
    ('the ninth cut passed an eval of another commit', 'release/fixtures/cut.v0-1-8.json',
     '"head_sha": "caa396523330ee0cc35ccb0bd42fbe1efa5c25aa",\n              "run_attempt": 1,\n              "workflow_id": 399025209',
     '"head_sha": "68efced8fd78641a239a6e5f41e0c81db6619684",\n              "run_attempt": 1,\n              "workflow_id": 399025209',
     NEXT_CUT_FIXTURE),
    ('the eval workflow ran another run on the ninth cut commit', 'release/fixtures/cut.v0-1-8.json',
     '\n                  "id": 43107717326,',
     '\n                  "id": 43107717327,',
     NEXT_CUT_FIXTURE),
]
