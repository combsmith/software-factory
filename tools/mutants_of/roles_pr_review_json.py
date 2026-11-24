"""The mutants of `roles/pr-review.json`: tools/mutants.py runs them."""

TARGETS = ("roles/pr-review.json",)
MUTANTS = [
    # Issue 481: the first signal stops the run, a later one stops neither the revocation nor the redaction, and the
    # script's own words reach OUT.
    ("the review Role does not permit its check run", "roles/pr-review.json",
     '"submit_review",\n        "create_check_run"\n', '"submit_review"\n',
     ("tests.test_tools.Authority.test_the_review_role_permits_its_check_run_now_its_app_is_granted_it",)),
]
