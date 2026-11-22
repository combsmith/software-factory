"""The mutants of `tools/hooks/before_stop.py`: tools/mutants.py runs them."""

TARGETS = ("tools/hooks/before_stop.py",)
MUTANTS = [
    # Issue 344: a hook's make run leaves nothing behind, and the stop hook starts no verify it cannot finish.
    ('a verify that did not finish is started again', 'tools/hooks/before_stop.py',
     '    if ago is not None:\n', '    if False:\n', ('tests.test_hooks.BeforeStop.test_a_verify_that_did_not_finish_is_not_started_again_for_a_while',)),
    ('a verify that ran out of time is written down as finished', 'tools/hooks/before_stop.py',
     '    note(record, now, not unfinished_now)\n',
     '    note(record, now, True)\n', ('tests.test_hooks.BeforeStop.test_a_verify_that_did_not_finish_is_not_started_again_for_a_while',)),
    ('a verify that finished is written down as unfinished', 'tools/hooks/before_stop.py',
     '    note(record, now, not unfinished_now)\n',
     '    note(record, now, False)\n', ('tests.test_hooks.BeforeStop.test_a_verify_that_did_not_finish_is_not_started_again_for_a_while',)),
    ('a verify is written down before it ends', 'tools/hooks/before_stop.py',
     '    budget = max(1, int(TIMEOUT - (time.monotonic() - asked)))\n',
     '    budget = max(1, int(TIMEOUT - (time.monotonic() - asked)))\n    note(record, now, False)\n', ('tests.test_hooks.BeforeStop.test_a_verify_that_did_not_finish_is_not_started_again_for_a_while',)),
    ('a verify that did not finish is never started again', 'tools/hooks/before_stop.py',
     '    return ago if 0 <= ago < RETRY else None\n', '    return ago if 0 <= ago else None\n', ('tests.test_hooks.BeforeStop.test_a_verify_that_did_not_finish_is_not_started_again_for_a_while',)),
    ('a flag is a start time', 'tools/hooks/before_stop.py',
     ' or isinstance(started, bool) or last.get("finished") is not False:', ' or last.get("finished") is not False:', ('tests.test_hooks.BeforeStop.test_a_verify_that_did_not_finish_is_not_started_again_for_a_while',)),
    ('any finish that is not true is no finish', 'tools/hooks/before_stop.py',
     ' or last.get("finished") is not False:', ' or last.get("finished"):', ('tests.test_hooks.BeforeStop.test_a_verify_that_did_not_finish_is_not_started_again_for_a_while',)),
    ('a start time after now is a run not finished', 'tools/hooks/before_stop.py',
     '    return ago if 0 <= ago < RETRY else None\n', '    return ago if ago < RETRY else None\n', ('tests.test_hooks.BeforeStop.test_a_verify_that_did_not_finish_is_not_started_again_for_a_while',)),
    ('a start time too large to read stops the hook', 'tools/hooks/before_stop.py',
     '    except OverflowError:\n        return None\n', '    except ZeroDivisionError:\n        return None\n', ('tests.test_hooks.BeforeStop.test_a_verify_that_did_not_finish_is_not_started_again_for_a_while',)),
    # Issue 438: the hooks run the checks alone, and a run that did not finish is no failure.
    ("the stop hook asks after another target", "tools/hooks/before_stop.py",
     '    if make.lacks("checks", where, env):\n', '    if make.lacks("verify", where, env):\n', ('tests.test_hooks.BeforeStop.test_a_branch_with_no_checks_target_tells_the_person_and_ends',)),
    ("the checks are read as failing when they ran out of time at a stop", "tools/hooks/before_stop.py",
     '    if unfinished_now:\n', '    if False:\n', ('tests.test_hooks.BeforeStop.test_a_verify_that_did_not_finish_is_not_started_again_for_a_while',)),
    ("a branch with no checks target is sent back", "tools/hooks/before_stop.py",
     '    if make.lacks("checks", where, env):\n', '    if False:\n', ('tests.test_hooks.BeforeStop.test_a_branch_with_no_checks_target_tells_the_person_and_ends',)),
    # The stop-hook review, 2026-11-05: each hook runs the main checkout's copy, and checks are not run twice at one state.
    # The stop-hook review, 2026-11-05: each hook runs the main checkout's copy, and checks are not run twice at one state.
    ('the stop hook runs the checks at every state', 'tools/hooks/before_stop.py',
     '    passed, said = make.checks(where, env, budget)\n', '    passed, said = make.make("checks", where, env, budget)\n', ('tests.test_hooks.SameTree.test_an_edit_and_the_stop_after_it_share_the_pass',)),
]
