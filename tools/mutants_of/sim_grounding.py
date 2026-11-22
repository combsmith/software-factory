"""The mutants of `sim/grounding.py`: tools/mutants.py runs them."""

TARGETS = ("sim/grounding.py",)
MUTANTS = [
    # #196 PR 2a: the pass's entry, its reads and the pass record's bound.
    ("a link by hand is grounded by no fixture", 'sim/grounding.py',
     '("P-61",), "trials/P-61.json", None),\n    # Seen in trials/P-48.json',
     '("P-61",), None, None),\n    # Seen in trials/P-48.json', ('tests.test_tools.Trials.test_p61_holds_what_grounds_its_three_rules',)),
    ("a pull request's close is grounded by no fixture", 'sim/grounding.py',
     'a reopening clears its closed_at",\n     ("P-61",), "trials/P-61.json", None),',
     'a reopening clears its closed_at",\n     ("P-61",), None, None),', ('tests.test_tools.Trials.test_p61_holds_what_grounds_its_three_rules',)),
    ("a type change is grounded by no fixture", 'sim/grounding.py',
     'and the type before and after", ("P-61",), "trials/P-61.json", None),',
     'and the type before and after", ("P-61",), None, None),', ('tests.test_tools.Trials.test_p61_holds_what_grounds_its_three_rules',)),
    # Decision 0233: the tracking issue no record numbers is told at its own read, by its opener and its body.
    ("the closing reference's rule is grounded by no fixture", 'sim/grounding.py',
     'one to another base carries no reference", ("P-33",), ("trials/P-33.json", "trials/P-33.port.json"), None),',
     'one to another base carries no reference", ("P-33",), None, None),', ('tests.test_tools.Trials.test_the_issue_fixtures_hold_what_grounds_the_four_rules',)),
]
