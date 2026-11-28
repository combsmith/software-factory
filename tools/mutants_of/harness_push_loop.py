"""The mutants of `harness/push_loop.py`: tools/mutants.py runs them."""

# The push loop's own pieces (issue 838; the Solution Architect's ruling 2 of 2026-11-28).
LANDS = ('tests.test_harness.PushLoop.test_both_of_p71s_pushes_land_through_send_into_seen',)
READ_AFTER = ('tests.test_harness.PushLoop.test_a_branch_write_is_followed_by_one_read_that_says_whose_a_422_is',)
PERMITS = ('tests.test_harness.PushLoop.test_a_request_leaves_only_as_the_guard_permits_it_by_the_pushs_own_sender',)
TREES = ('tests.test_harness.PushLoop.test_a_trees_answer_is_the_ports_listing_or_its_code',)
ORDERED = ('tests.test_harness.PushLoop.test_the_checks_before_the_first_write_are_asked_in_their_order_and_none_is_skipped',)
LOOP_PY = 'harness/push_loop.py'

TARGETS = (LOOP_PY,)
MUTANTS = [
    # One request, asked of the guard unchanged, sent by the push's own sender, and seen.
    ("a request leaves that the guard does not permit", LOOP_PY,
     ' or not guard.permits(state, req["method"], req["path"], req["body"]):\n',
     ':\n', PERMITS),
    ("a request in no shape is asked of the guard", LOOP_PY,
     '    if not _request(req) or not guard.permits(',
     '    if not guard.permits(', PERMITS),
    ("a request with no body is read as one", LOOP_PY,
     ' and type(req.get("path")) is str and "body" in req\n',
     ' and type(req.get("path")) is str\n', PERMITS),
    ("a tree's answer is not read through the port's listing", LOOP_PY,
     '    if req["method"] == GET and TREES in req["path"]:\n',
     '    if False:\n', LANDS),
    ("a listing's code is passed over", LOOP_PY,
     '        if why is not None:\n            return None, why\n    return guard.seen(',
     '    return guard.seen(', TREES),
    ("a tree is listed at a name cut short", LOOP_PY,
     '[1][:len(guard.SHA)])\n',
     '[1][:len(guard.SHA) - 1])\n', LANDS),
    # A branch's write, then the branch read once more.
    ("the branch is not read again after its write", LOOP_PY,
     '    return step(state, sender, repo, branch, port.read_branch(repo, branch))\n',
     '    return state, None\n', READ_AFTER),
    ("a refused write is followed by the read", LOOP_PY,
     '    state, why = step(state, sender, repo, branch, write)\n    if why is not None:\n        return None, why\n',
     '    state, why = step(state, sender, repo, branch, write)\n', READ_AFTER),
    # The checks before the first write, in their order, none skipped.
    ("checks in another order are asked", LOOP_PY,
     ' and len(pair) == 2 and pair[0] for pair in checks] \\\n            != list(ORDER):\n',
     ' and len(pair) == 2 and pair[0] for pair in checks] \\\n            != [pair[0] for pair in checks]:\n', ORDERED),
    ("a check's refusal is passed over", LOOP_PY,
     '        if why is not None:\n            return why if',
     '        if False:\n            return why if', ORDERED),
    ("a check's answer of another kind is taken as its code", LOOP_PY,
     '            return why if type(why) is str and why else guard.NOT_PERMITTED\n',
     '            return why\n', ORDERED),
    ("checks of another kind are read", LOOP_PY,
     '    if type(checks) not in (list, tuple) or ',
     '    if ', ORDERED),
]
