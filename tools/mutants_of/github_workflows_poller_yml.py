"""The mutants of `.github/workflows/poller.yml`: tools/mutants.py runs them."""

TARGETS = (".github/workflows/poller.yml",)
MUTANTS = [
    ("the live poller takes an input", '.github/workflows/poller.yml',
     '  workflow_dispatch:\n', '  workflow_dispatch:\n    inputs:\n      item:\n        type: string\n', ('tests.test_tools.Workflows.test_the_pollers_shim_stands_as_its_template_and_its_hash',)),
    ("the live poller wakes on no tick", '.github/workflows/poller.yml',
     '  schedule:\n    - cron: "13 * * * *"\n    - cron: "33 * * * *"\n    - cron: "53 * * * *"\n', '', ('tests.test_tools.Workflows.test_the_pollers_shim_stands_as_its_template_and_its_hash',)),
    ("the live poller's pass may be cancelled", '.github/workflows/poller.yml',
     'cancel-in-progress: false', 'cancel-in-progress: true', ('tests.test_tools.Workflows.test_the_pollers_shim_stands_as_its_template_and_its_hash',)),
    ("the live poller calls another file than the pass", '.github/workflows/poller.yml',
     '/pass.yml@', '/eval.yml@', ('tests.test_tools.Workflows.test_the_pollers_shim_stands_as_its_template_and_its_hash',)),
]
