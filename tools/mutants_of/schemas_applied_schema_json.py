"""The mutants of `schemas/applied.schema.json`: tools/mutants.py runs them."""

TARGETS = ("schemas/applied.schema.json",)
MUTANTS = [
    # Issue 838: the opening Run's draft is the model's title and body alone, each bounded here by GitHub's limits.
    ('applied/1 records no opening', 'schemas/applied.schema.json',
     '              "push_commits",\n              "open_pull_request",\n              "submit_review",\n',
     '              "push_commits",\n              "submit_review",\n',
     ('tests.test_approve.Records.test_an_approval_is_an_effect_apply_records_and_no_result_may_ask_for',)),
]
