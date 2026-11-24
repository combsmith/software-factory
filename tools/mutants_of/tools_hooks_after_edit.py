"""The mutants of `tools/hooks/after_edit.py`: tools/mutants.py runs them."""

TARGETS = ("tools/hooks/after_edit.py",)
MUTANTS = [
    # Issue 438: the hooks run the checks alone, and a run that did not finish is no failure.
    ("the edit hook asks after another target", "tools/hooks/after_edit.py",
     '    if make.lacks("checks", where, env):\n', '    if make.lacks("fast", where, env):\n', ('tests.test_hooks.AfterEdit.test_a_branch_with_no_checks_target_tells_the_person_and_does_not_fail',)),
    ("the checks are read as failing when they ran out of time after an edit", "tools/hooks/after_edit.py",
     '    if make.ran_out(said, "checks", where):\n', '    if False:\n', ('tests.test_hooks.AfterEdit.test_checks_that_ran_out_of_time_found_nothing_and_say_so',)),
    # The stop-hook review, 2026-11-05: each hook runs the main checkout's copy, and checks are not run twice at one state.
    # The stop-hook review, 2026-11-05: each hook runs the main checkout's copy, and checks are not run twice at one state.
    ('the edit hook runs the checks at every state', 'tools/hooks/after_edit.py',
     '    passed, said = make.checks(where, env, TIMEOUT)\n', '    passed, said = make.make("checks", where, env, TIMEOUT)\n', ('tests.test_hooks.SameTree.test_an_edit_and_the_stop_after_it_share_the_pass',)),
]
