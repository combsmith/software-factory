"""The mutants of `.github/workflows/queue.yml`: tools/mutants.py runs them."""

TARGETS = (".github/workflows/queue.yml",)
MUTANTS = [
    ("the live queue act's shim starts from any dispatcher", '.github/workflows/queue.yml',
     "github.actor_id == '41898282' && ", '',
     ('tests.test_tools.Workflows.test_the_shims_that_dispatch_a_run_stand_as_their_templates_and_their_hashes',)),
]
