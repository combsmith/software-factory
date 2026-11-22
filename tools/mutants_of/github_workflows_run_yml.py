"""The mutants of `.github/workflows/run.yml`: tools/mutants.py runs them."""

TARGETS = (".github/workflows/run.yml",)
MUTANTS = [
    ("the live Run's shim runs a re-run", '.github/workflows/run.yml',
     " && github.run_attempt == '1'", '',
     ('tests.test_tools.Workflows.test_the_shims_that_dispatch_a_run_stand_as_their_templates_and_their_hashes',)),
]
