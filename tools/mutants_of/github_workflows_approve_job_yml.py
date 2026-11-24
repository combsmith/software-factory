"""The mutants of `.github/workflows/approve-job.yml`: tools/mutants.py runs them."""

TARGETS = (".github/workflows/approve-job.yml",)
MUTANTS = [
    # Issue 757: the run record says whether a Run's Engine step started, from the outcome apply writes.
    ("the act checks out the tag again", '.github/workflows/approve-job.yml',
     '          ref: ${{ job.workflow_sha }}\n', '          ref: factory/v0-next\n',
     ('tests.test_tools.Workflows.test_the_approving_act_holds_the_approvers_token_alone',)),
]
