"""The mutants of `release/fixtures/cut.v0-1-0.json`: tools/mutants.py runs them."""

CUT_FIXTURE = ("tests.test_release.Fixture.test_the_first_cut_moved_next_and_its_release_is_neither_moved_nor_cut_again",)

TARGETS = ("release/fixtures/cut.v0-1-0.json",)
MUTANTS = [
    # The fourteenth cut's fixture, v0.1.13 at #859's merge: the same reads, next's Deployments as a page of four, the
    # thirteenth cut's Deployment below its own and v0.1.12 left where it was.
    ('a Release tag may be moved', 'release/fixtures/cut.v0-1-0.json',
     '"enforcement": "active"', '"enforcement": "evaluate"', CUT_FIXTURE),
    ('an admin may force a Release tag to another commit', 'release/fixtures/cut.v0-1-0.json',
     '"status": 422', '"status": 200', CUT_FIXTURE),
    ('the refused PATCH did not force', 'release/fixtures/cut.v0-1-0.json', '"force": true', '"force": false',
     CUT_FIXTURE),
    ('the refused PATCH asked for the commit the tag already names', 'release/fixtures/cut.v0-1-0.json',
     '"sha": "a32c0cebd32a28f0c2e369e2dd3f69a7ebfcbdce"', '"sha": "499835d5384ba81c466b17199edcde1848431630"',
     CUT_FIXTURE),
    ('the tag was read before the PATCH it is said to follow', 'release/fixtures/cut.v0-1-0.json',
     '13:07:04 GMT', '23:07:04 GMT', CUT_FIXTURE),
    ('the tag ruleset exempts the Release', 'release/fixtures/cut.v0-1-0.json',
     '"exclude": []', '"exclude": ["refs/tags/factory/v0.1.0"]', CUT_FIXTURE),
    # Muse's read of #617: the PATCH is the Maintainer's admin role's, refused as a protected ref, and the ruleset holds
    # the rules tools/check_rulesets.py holds it to.
    ('the refused PATCH is no admin role\'s', 'release/fixtures/cut.v0-1-0.json', ', the admin role)', ')', CUT_FIXTURE),
    ('the PATCH is refused for another reason', 'release/fixtures/cut.v0-1-0.json',
     'Cannot update this protected ref.', 'Cannot do that.', CUT_FIXTURE),
    ('the tag ruleset need not refuse a force-push', 'release/fixtures/cut.v0-1-0.json',
     '"type": "non_fast_forward"', '"type": "creation"', CUT_FIXTURE),
]
