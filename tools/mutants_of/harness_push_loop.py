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
     '    if not _request(req) or not guard.permits(state, req["method"], req["path"], req["body"]) \\\n',
     '    if not _request(req) \\\n', PERMITS),
    ("a request leaves for another push's branch", LOOP_PY,
     '            or [repo, branch] != [state["push"]["repo"], state["push"]["branch"]]:\n',
     '            or repo != state["push"]["repo"]:\n', PERMITS),
    ("a request with a key the port never builds is sent", LOOP_PY,
     ' and set(req) <= port.REQUEST and ',
     ' and ', PERMITS),
    ("a request with no body is read as one", LOOP_PY,
     ' and type(req.get("path")) is str and "body" in req\n',
     ' and type(req.get("path")) is str\n', PERMITS),
    ("a tree's answer is not read through the port's listing", LOOP_PY,
     '    if req["method"] == GET and req["path"].startswith(trees):\n',
     '    if False:\n', LANDS),
    ("a tree read is told by its path's middle", LOOP_PY,
     '    if req["method"] == GET and req["path"].startswith(trees):\n',
     '    if req["method"] == GET and TREES in req["path"]:\n', PERMITS),
    ("a listing's code is passed over", LOOP_PY,
     '        if why is not None:\n            return None, why\n    return guard.seen(',
     '    return guard.seen(', TREES),
    ("a tree is listed at a name cut short", LOOP_PY,
     '[len(trees):len(trees) + len(guard.SHA)])\n',
     '[len(trees):len(trees) + len(guard.SHA) - 1])\n', LANDS),
    # A branch's write, then the branch read once more.
    ("the branch is not read again after its write", LOOP_PY,
     '    return step(state, sender, repo, branch, port.read_branch(repo, branch))\n',
     '    return state, None\n', READ_AFTER),
    ("a refused write is followed by the read", LOOP_PY,
     '    state, why = step(state, sender, repo, branch, write)\n    if why is not None:\n        return None, why\n',
     '    state, why = step(state, sender, repo, branch, write)\n', READ_AFTER),
    # The checks before the first write, in their order, none skipped.
    ("checks in another order are asked", LOOP_PY,
     ' and pair[0] for pair in checks] != list(ORDER) \\\n',
     ' and pair[0] for pair in checks] != [pair[0] for pair in checks] \\\n', ORDERED),
    ("a list changed while it is asked asks less", LOOP_PY,
     '    checks = tuple(checks) if type(checks) in (list, tuple) else ()\n',
     '    checks = checks if type(checks) in (list, tuple) else ()\n', ORDERED),
    ("a check that cannot be called is asked about", LOOP_PY,
     ' \\\n            or not all(callable(check) for _, check in checks):\n',
     ':\n', ORDERED),
    ("a check's refusal is passed over", LOOP_PY,
     '        if why is not None:\n            return why if',
     '        if False:\n            return why if', ORDERED),
    ("a sentence is taken as a check's code", LOOP_PY,
     '            return why if type(why) is str and CODE.fullmatch(why) else guard.NOT_PERMITTED\n',
     '            return why if type(why) is str and why else guard.NOT_PERMITTED\n', ORDERED),
    ("checks of another kind are read", LOOP_PY,
     '    checks = tuple(checks) if type(checks) in (list, tuple) else ()\n',
     '    checks = tuple(checks)\n', ORDERED),
]
