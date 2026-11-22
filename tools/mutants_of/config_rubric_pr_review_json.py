"""The mutants of `config/rubric-pr-review.json`: tools/mutants.py runs them."""

TARGETS = ("config/rubric-pr-review.json",)
MUTANTS = [
    # Issue 974: whose words they are by the account alone, markers in GitHub's own forms, and the read's shapes.
    ("a logic error falls under no criterion", 'config/rubric-pr-review.json', 'The change does what it means to, with no logic error, and new behaviour', 'New behaviour',
     ("tests.test_evals.EvalJob.test_the_review_is_told_to_cite_and_what_met_means",)),
    ("PR-3 asks for what no Task holds", 'config/rubric-pr-review.json', '"evidence": "The diff.",\n      "severity_if_violated": "major"', '"evidence": "The diff and the test results.",\n      "severity_if_violated": "major"',
     ("tests.test_evals.EvalJob.test_the_review_is_told_to_cite_and_what_met_means",)),
]
