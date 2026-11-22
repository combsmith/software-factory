"""The mutants of `docs/architecture/software-factory-design.md`: tools/mutants.py runs them."""

TARGETS = ("docs/architecture/software-factory-design.md",)
MUTANTS = [
    # P-31 is the relay's trial, not the first approval's (decision 0107).
    ("the relay's host stands before any code", 'docs/architecture/software-factory-design.md',
     "| **1. Before any code** | ", "| **1. Before any code** | P-31; ", ('tests.test_tools.Trials.test_the_relays_host_stands_in_no_batch_before_the_first_approval',)),
    ("section 6.1 does not say why the first approval goes without the relay", 'docs/architecture/software-factory-design.md',
     " The first approval does not need W-2, since a Run's end starts its passes (decision 0043).", "", ('tests.test_tools.Trials.test_the_relays_host_stands_in_no_batch_before_the_first_approval',)),
    ("the relay's host stands before the first approval", 'docs/architecture/software-factory-design.md',
     "| P-9, P-20 (chaining and the outside tick", "| P-9, P-20, P-31 (chaining and the outside tick", ('tests.test_tools.Trials.test_the_relays_host_stands_in_no_batch_before_the_first_approval',)),
]
