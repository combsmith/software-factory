"""The mutants of `.github/workflows/approve.yml`: tools/mutants.py runs them."""

TARGETS = (".github/workflows/approve.yml",)
MUTANTS = [
    ("the live approving act's shim starts under a Pause", '.github/workflows/approve.yml',
     " && (vars.FACTORY_PAUSED == '' || vars.FACTORY_PAUSED == 'false')", '',
     ('tests.test_tools.Workflows.test_the_shims_that_dispatch_a_run_stand_as_their_templates_and_their_hashes',)),
]
