"""The mutants of `controller/issue_holds.py`: tools/mutants.py runs them."""

TARGETS = ("controller/issue_holds.py",)
MUTANTS = [
    # Decision 0232: a pull request the Factory opened stands with its issue, held while a person holds or has closed it.
    ('an issue two pull requests name is read twice', 'controller/issue_holds.py',
     '        if number is not None and number not in numbers:\n',
     '        if number is not None:\n', ('tests.test_controller.Entry.test_each_pull_request_opened_for_an_issue_is_told_how_its_issue_stands',)),
    ('how an issue stands is never filled', 'controller/issue_holds.py',
     '        out.append(dict(entry, facts=dict(entry["facts"], issue_stands=issue.stands(stood.get(number), config))))\n',
     '        out.append(entry)\n', ('tests.test_controller.Entry.test_each_pull_request_opened_for_an_issue_is_told_how_its_issue_stands',)),
    ('a pull request opened for no issue is told how an issue stands', 'controller/issue_holds.py',
     '        if number is None:\n            out.append(entry)\n            continue\n',
     '', ('tests.test_controller.Entry.test_each_pull_request_opened_for_an_issue_is_told_how_its_issue_stands',)),
]
