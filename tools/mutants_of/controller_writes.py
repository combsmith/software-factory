"""The mutants of `controller/writes.py`: tools/mutants.py runs them."""

TARGETS = ("controller/writes.py",)
MUTANTS = [
    # GitHub's index lines of one compare, 8 characters long at one read and 9 at the next, are one content (2026-11-19).
    ('the successor is planned before the dispatches', 'controller/writes.py',
     '    for dispatch in out["dispatch"]:',
     '    if out["successor"]:\n        add("dispatch_successor", None)\n    for dispatch in out["dispatch"]:', ('tests.test_effects',)),
    ('an approval is planned as a Run', 'controller/writes.py',
     '"dispatch_queue" if decision.get("action") in QUEUE_INTENTS else "dispatch_approval"',
     '"dispatch_queue" if decision.get("action") in QUEUE_INTENTS else "dispatch_run"', ('tests.test_effects',)),
    ('an act no write serves is dropped from the plan', 'controller/writes.py',
     '    for act in out["acts"]:\n        add("not_built", act["item"], action=act["action"])\n',
     '', ('tests.test_effects',)),
    # Issue 362: the org's Pause read from the repo's list of the org's variables, as P-52 found.
    ('the tracking issue is not planned', 'controller/writes.py',
     '    add("tracking_issue", None)\n',
     '', ('tests.test_effects.Plan.test_the_writes_go_in_their_order',)),
    # #193's ruling 6: the status on the item, and what a pass carries for it.
    ('a plan with a status and no head', 'controller/writes.py',
     'if e.get("head"):\n            add("status_on_item"',
     'if True:\n            add("status_on_item"', ('tests.test_effects.Status',)),
    # Issue 381, the queue step's first part: each queue act a dispatched Run of the queue workflow once it is named.
    ('a dequeue is sent as an enqueue', 'controller/writes.py',
     '"dequeue": t.DEQUEUE_MERGE,',
     '"dequeue": t.ENQUEUE_MERGE,', ('tests.test_controller.Record.test_a_queue_act_gets_a_run_id_and_a_dispatch_once_its_workflow_is_named',)),
    ("a queue act is sent with no queue App's account", 'controller/writes.py',
     '    return file if file is not None and account is not None else None',
     '    return file', ('tests.test_controller.Record.test_a_queue_act_gets_a_run_id_and_a_dispatch_once_its_workflow_is_named',)),
    ('a queue act is planned as an approval', 'controller/writes.py',
     '"dispatch_queue" if decision.get("action") in QUEUE_INTENTS else "dispatch_approval"',
     '"dispatch_approval" if decision.get("action") in QUEUE_INTENTS else "dispatch_approval"', ('tests.test_effects.Effects.test_a_queue_act_is_dispatched_to_the_queue_workflow_once_it_is_named',)),
]
