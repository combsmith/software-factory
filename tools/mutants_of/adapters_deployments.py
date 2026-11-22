"""The mutants of `adapters/deployments.py`: tools/mutants.py runs them."""

TARGETS = ("adapters/deployments.py",)
MUTANTS = [
    # The release workflow's step and its ports (#197, PR 2a).
    ('a Deployment of another commit counts', 'adapters/deployments.py',
     ' or body.get("sha") != commit',
     '', ('tests.test_release_step.Writes.test_a_deployment_of_next_is_recorded_with_its_status',)),
    ('a Deployment whose status failed counts', 'adapters/deployments.py',
     ' or body.get("state") != "success":',
     ':', ('tests.test_release_step.Writes.test_a_deployment_of_next_is_recorded_with_its_status',)),
    ('a Deployment to another environment counts', 'adapters/deployments.py',
     ' \\\n                or body.get("environment") != ENVIRONMENT:',
     ':', ('tests.test_release_step.Writes.test_a_deployment_of_next_is_recorded_with_its_status',)),
    ('a status not created counts', 'adapters/deployments.py',
     '    if answer["status"] != 201 or not isinstance(body, dict)',
     '    if not isinstance(body, dict)', ('tests.test_release_step.Writes.test_a_deployment_of_next_is_recorded_with_its_status',)),
    # Muse's second-family reads of #340, #354 and #358 (decision 0080).
    ('a Deployment answered with no 201 is made', 'adapters/deployments.py',
     'answer["status"] == 201 and isinstance(body, dict)', 'isinstance(body, dict)', ('tests.test_release_step.Writes.test_a_deployment_of_next_is_recorded_with_its_status',)),
    # Argon's reads of #354 and #358, owed while it had no quota (no record; Boundaries rows on 0073 and 0076).
    ('a Deployment of id 0 is recorded', 'adapters/deployments.py',
     'if type(ident) is not int or ident < 1 or', 'if type(ident) is not int or', ('tests.test_release_step.Writes.test_a_deployment_of_next_is_recorded_with_its_status',)),
    # The review round of #397: the home's repo and branch are read as text, and an id of True is no id.
    ('a Deployment of id True is recorded', 'adapters/deployments.py',
     'if type(ident) is not int or ident < 1 or', 'if not isinstance(ident, int) or ident < 1 or', ('tests.test_release_step.Writes.test_a_deployment_of_next_is_recorded_with_its_status',)),
]
