"""The mutants of `.github/workflows/pass.yml`: tools/mutants.py runs them."""

TARGETS = (".github/workflows/pass.yml",)
MUTANTS = [
    # Decision 0123: a called workflow checks out its own commit.
    ("the pass checks out the tag again", '.github/workflows/pass.yml',
     '          ref: ${{ job.workflow_sha }}\n', '          ref: factory/v0-next\n',
     ('tests.test_tools.Workflows.test_the_pass_uploads_its_record_before_it_dispatches',)),
]
