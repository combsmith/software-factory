"""The mutants of `release/fixtures/rollback.refused.json`: tools/mutants.py runs them."""

ROLLBACK_FIXTURE = ("tests.test_release.Fixture.test_a_rollback_with_no_earlier_release_was_refused_and_moved_nothing",)

TARGETS = ("release/fixtures/rollback.refused.json",)
MUTANTS = [
    # Muse's read of #627: the refused rollback's evidence is read only where GitHub answered it.
    ('the refused rollback\'s deployments are read from a refused answer', 'release/fixtures/rollback.refused.json',
     'deployments?environment=factory-next (gh api --include)",\n            "headers": {\n              "accept": "application/vnd.github+json"\n            },\n            "body": null\n          },\n          "response": {\n            "status": 200,',
     'deployments?environment=factory-next (gh api --include)",\n            "headers": {\n              "accept": "application/vnd.github+json"\n            },\n            "body": null\n          },\n          "response": {\n            "status": 500,', ('tests.test_release.Fixture.test_a_rollback_with_no_earlier_release_was_refused_and_moved_nothing',)),
    # The refused rollback's fixture: the rules refuse it for every tag read after it, and it moved and recorded nothing.
    ('a rollback with no earlier Release moved next', 'release/fixtures/rollback.refused.json',
     '"ref": "refs/tags/factory/v0-next",\n              "object": {\n                "sha": "499835d5',
     '"ref": "refs/tags/factory/v0-next",\n              "object": {\n                "sha": "9ca55015', ROLLBACK_FIXTURE),
    ('an earlier Release stood beside the one next names', 'release/fixtures/rollback.refused.json',
     '            {\n                "ref": "refs/tags/factory/v0.1.0",',
     '            {"ref": "refs/tags/factory/v0.0.9", "object": {"sha": "9ca550156d2d34672ec6496cacc00b29dc20c76e", '
     '"type": "commit"}},\n            {\n                "ref": "refs/tags/factory/v0.1.0",', ROLLBACK_FIXTURE),
    ('the Deployment is dated after the refused rollback', 'release/fixtures/rollback.refused.json',
     '"transient_environment": false,\n                "created_at": "2026-11-07T06:48:42Z"',
     '"transient_environment": false,\n                "created_at": "2026-11-07T19:11:52Z"', ROLLBACK_FIXTURE),
    ("the Deployment's status is dated after the refused rollback", 'release/fixtures/rollback.refused.json',
     '"state": "success",\n                "environment": "factory-next",\n                "description": "",\n'
     '                "created_at": "2026-11-07T06:48:42Z"',
     '"state": "success",\n                "environment": "factory-next",\n                "description": "",\n'
     '                "created_at": "2026-11-07T19:11:52Z"', ROLLBACK_FIXTURE),
    ('the tags were read before the rollback ended', 'release/fixtures/rollback.refused.json',
     '"updated_at": "2026-11-07T19:11:56Z"', '"updated_at": "2026-11-07T19:23:56Z"', ROLLBACK_FIXTURE),
]
