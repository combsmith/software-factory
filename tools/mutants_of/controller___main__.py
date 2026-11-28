"""The mutants of `controller/__main__.py`: tools/mutants.py runs them."""

TARGETS = ("controller/__main__.py",)
MUTANTS = [
    # Decision 0224: the run records read each review Run's advisory cost, and the pass tells each review whether the day admits it.
    ('the pass asks for no advisory cost', 'controller/__main__.py',
     '                                advised=records.advised(earlier), day=now[:len("2026-01-01")],\n',
     '', ('tests.test_controller.Entry.test_a_merged_pull_requests_unmatched_write_alarms_inside_the_window_and_not_past_it',)),
    ('the pass asks for every advisory cost again', 'controller/__main__.py',
     'advised=records.advised(earlier), day=',
     'day=', ('tests.test_controller.Entry.test_a_merged_pull_requests_unmatched_write_alarms_inside_the_window_and_not_past_it',)),
    ("the pass keeps only the later record's advisory costs", 'controller/__main__.py',
     'advised=records.advised(earlier), day=',
     'advised=records.advised(earlier[-1:]), day=', ('tests.test_controller.Entry.test_a_merged_pull_requests_unmatched_write_alarms_inside_the_window_and_not_past_it',)),
]
