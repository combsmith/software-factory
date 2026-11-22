"""The mutants of `examples/decision.path-needs-person.json`: tools/mutants.py runs them."""

TARGETS = ("examples/decision.path-needs-person.json",)
MUTANTS = [
    # A change to a path only a person decides waits under its own code (issue 746, decision 0207).
    ("the example of a person-only path's Decision is a model Lens's input's", 'examples/decision.path-needs-person.json',
     '  "reason": "path_needs_person",\n',
     '  "reason": "model_lens_input_needs_person",\n',
     ('tests.test_decide.TheFactorysOwnRules.test_a_change_to_a_path_only_a_person_decides_waits_for_a_person',)),
]
