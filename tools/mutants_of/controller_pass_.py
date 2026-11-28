"""The mutants of `controller/pass_.py`: tools/mutants.py runs them."""

TARGETS = ("controller/pass_.py",)
MUTANTS = [
    # Decision 0224: the run records read each review Run's advisory cost, and the pass tells each review whether the day admits it.
    ('a review admitted earlier in the pass counts nothing against the day', 'controller/pass_.py',
     'advisory_.admits(runs + asking, whole, now,',
     'advisory_.admits(runs, whole, now,', ('tests.test_controller.Record.test_an_admitted_review_is_told_beside_its_decision_whether_the_day_admits_its_readers',)),
    ('no review is told whether the day admits its readers', 'controller/pass_.py',
     '        if d["outcome"] == t.ADMIT and d["admit"]["intent"] == advisory_.REVIEWING:\n',
     '        if False:\n', ('tests.test_controller.Record.test_an_admitted_review_is_told_beside_its_decision_whether_the_day_admits_its_readers',)),
    ('the pass answers for the day without the configuration', 'controller/pass_.py',
     'whole, now, config.get("harness") or {})',
     'whole, now, {})', ('tests.test_controller.Record.test_an_admitted_review_is_told_beside_its_decision_whether_the_day_admits_its_readers',)),
    ('an admission of any Intent is told whether the day admits its readers', 'controller/pass_.py',
     '        if d["outcome"] == t.ADMIT and d["admit"]["intent"] == advisory_.REVIEWING:\n',
     '        if d["outcome"] == t.ADMIT:\n', ('tests.test_controller.Record.test_an_admitted_review_is_told_beside_its_decision_whether_the_day_admits_its_readers',)),
    ("the reviews admitted before in a pass count without the day's spend", 'controller/pass_.py',
     'advisory_.admits(runs + asking, whole, now,',
     'advisory_.admits(asking or runs, whole, now,', ('tests.test_controller.Record.test_an_admitted_review_is_told_beside_its_decision_whether_the_day_admits_its_readers',)),
    ('an entry that admits no review counts against the day', 'controller/pass_.py',
     '            asking.append({"intent": advisory_.REVIEWING, "started_at": now})\n',
     '        asking.append({"intent": advisory_.REVIEWING, "started_at": now})\n', ('tests.test_controller.Record.test_an_admitted_review_is_told_beside_its_decision_whether_the_day_admits_its_readers',)),
]
