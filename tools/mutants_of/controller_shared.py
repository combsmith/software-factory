"""The mutants of `controller/shared.py`: tools/mutants.py runs them."""

TARGETS = ("controller/shared.py",)
MUTANTS = [
    # The Controller's pass, issue 193's first pull request: one mutant to a rule of controller/, or more.
    ("an issue's page is a pull request's", 'controller/shared.py',
     'else "issues"',
     'else "pull"', ('tests.test_controller.Record.test_an_issue_is_asked_of_the_issues_kernel_with_its_own_lifecycle',)),
    # Issue 837: the served issues' writes are read for reconciliation, and matched as a pull request's are.
    ("a write on an issue is named by a pull request's page", 'controller/shared.py',
     'kind = "pull" if item["type"] == "pull_request" else "issues"', 'kind = "pull"', ('tests.test_reconcile.Matching.test_a_write_on_an_issue_is_matched_as_one_on_a_pull_request_is',)),
]
