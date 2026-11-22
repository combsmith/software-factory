"""The mutants of `tests/test_transitions.py`: tools/mutants.py runs them."""

TARGETS = ("tests/test_transitions.py",)
MUTANTS = [
    # Issue 757: a Role's Run that ended environment or never started is counted apart from the Run ceiling.
    ("the explorer reads a conflict only through unknown", "tests/test_transitions.py",
     'lambda pr: set_fact(mergeable=False, queue=False)(pr) if pr["facts"]["mergeable"] is True else None),',
     'lambda pr: set_fact(mergeable=False, queue=False)(pr) if pr["facts"]["mergeable"] is False else None),',
     ("tests.test_transitions.Transitions.test_a_conflict_worked_out_at_once_is_explored",)),
    # Issue 962: a conflict the base's next move clears at once, and the platform's ending of a ceiling Hold.
    ("the explorer's base move clears no conflict at once", "tests/test_transitions.py",
     'lambda pr: set_fact(mergeable=True)(pr) if pr["facts"]["mergeable"] is False else None),',
     'lambda pr: None if pr["facts"]["mergeable"] is False else None),', ('tests.test_transitions.Transitions.test_a_conflict_that_clears_at_once_is_explored',)),
    ('the queue keeps a pull request that conflicts at once', "tests/test_transitions.py",
     'lambda pr: set_fact(mergeable=False, queue=False)(pr) if pr["facts"]["mergeable"] is True else None),',
     'lambda pr: set_fact(mergeable=False)(pr) if pr["facts"]["mergeable"] is True else None),',
     ("tests.test_transitions.Transitions.test_a_conflict_worked_out_at_once_is_explored",)),
    # Issue 950, items 5 and 6: a resolved thread is said dropped again by the next review, and I-11 as the Kernel's due.
    ("the explorer's push that keeps the diff gives the default diff", "tests/test_transitions.py",
     '    diff = f["diff"] if keep else diff or {"files": 2, "lines": 40, "truncated": False, "characters": 1600}\n',
     '    diff = diff or {"files": 2, "lines": 40, "truncated": False, "characters": 1600}\n', ('tests.test_transitions.Transitions.test_a_push_that_leaves_the_diff_as_it_was_asks_a_gating_lens_again',)),
    ("the explorer's push that keeps the diff gives new content", "tests/test_transitions.py",
     '    content = f["content_id"] if keep else "sha256:%04x" % pr["minute"]\n',
     '    content = "sha256:%04x" % pr["minute"]\n', ('tests.test_transitions.Transitions.test_a_push_that_leaves_the_diff_as_it_was_asks_a_gating_lens_again',)),
]
