"""The mutants of `harness/approve_step.py`: tools/mutants.py runs them."""

TARGETS = ("harness/approve_step.py",)
MUTANTS = [
    # Issue 342: a pull request the Factory opens is bound to its issue by the Run that opened it, as well as its branch.
    ("the approver hands its read again no pass record", 'harness/approve_step.py',
     '                                           record=record),', '                                           ),',
     ('tests.test_steps.Approve.test_the_approver_holds_to_its_item',)),
    # Muse's read of #194's PR 3.
    ("the approver's reads go through its token unheld", 'harness/approve_step.py',
     'approving = effects.Approving(transport, parts["item"])',
     'approving = transport', ('tests.test_steps.Approve.test_the_approver_holds_to_its_item',)),
    ('the approving act is told another approver', 'harness/approve_step.py',
     '"approver": config["kernel"]["approver"]',
     '"approver": "someone-else"', ('tests.test_steps.Approve.test_the_approver_holds_to_its_item',)),
    # The Claude review of #196 PR 2b-1.
    ("an approval's fault concludes the Run a success", 'harness/approve_step.py',
     '    if ended["outcome"] is not None:\n        raise Stop(ended["reason"] or ended["outcome"])\n',
     '', ('tests.test_steps.Approve.test_the_approver_holds_to_its_item',)),
    ('the approving act takes a Decision of another item', 'harness/approve_step.py',
     'read_.decided(record, parts, config["kernel"]["owner_role"])',
     'None', ('tests.test_steps.Approve.test_the_approver_holds_to_its_item',)),
    ('the approving act reads a record that cannot be read as none', 'harness/approve_step.py',
     '        return approve._records(parts["run"], release, "refused", None, ("environment", "record_unreadable"))',
     '        record = None', ('tests.test_steps.Approve.test_the_approver_holds_to_its_item',)),
    # Argon on #196 PR 2b-1.
    ('the approver reads the item again through its token unheld', 'harness/approve_step.py',
     'lambda: reread.item(approving, config,',
     'lambda: reread.item(transport, config,', ('tests.test_steps.Approve.test_the_approver_holds_to_its_item',)),
    # The approving act names a Pause the port could not read by the port's part (#688's seventh dry run, decision
    # 0192).
    ("the approving act asks the read again for no part of the Pause", 'harness/approve_step.py',
     'utc(), utc, name_pause=True,', 'utc(), utc,', ('tests.test_steps.Approve.test_the_approver_holds_to_its_item',)),
    # Muse on #196 PR 2b-1.
    ("the approving act approves under another Release than its pass's", 'harness/approve_step.py',
     'if record is not None and record.get("release") != release:',
     'if False:', ('tests.test_steps.Approve.test_the_approver_holds_to_its_item',)),
    # #196 PR 2b-2: the Release a step runs as, read from its checkout's one Release tag.
    ('the act runs as a Release it did not read', 'harness/approve_step.py',
     '    release = steps.release()\n',
     '    release = "factory/v0.3.1"\n', ('tests.test_steps.ReleaseName.test_a_step_with_no_release_reads_no_key',)),
]
