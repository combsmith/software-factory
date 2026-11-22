"""The mutants of `harness/shared.py`: tools/mutants.py runs them."""

TARGETS = ("harness/shared.py",)
MUTANTS = [
    # Pull request 688, the dry run: a read GitHub did not answer is named by a code of the Harness's own.
    ("a read no stage named is named one", "harness/shared.py",
     '        return "facts_unreadable"\n', '        return "snapshot_unreadable"\n', ('tests.test_steps.Reader.test_the_reader_fails_closed',)),
    ("a stage's code drops the snapshot's part", "harness/shared.py",
     '"%s_%s_unreadable" % (stage, part) if part else ', '', ('tests.test_steps.Reader.test_the_reader_fails_closed',)),
    ("a read is told no stage", "harness/shared.py",
     '        err.stage = stage\n', '        pass\n', ('tests.test_steps.Reader.test_the_reader_fails_closed',)),
    # A fault of a read's own code is named as a read GitHub refused is (#688's sixth dry run, decision 0187).
    ("a stage names a read GitHub refused and no other fault", "harness/shared.py",
     '    except Exception as err:\n        err.stage = stage\n        raise\n',
     '    except Exception as err:\n        from adapters.github import Unanswered\n        if isinstance(err, Unanswered):\n            err.stage = stage\n        raise\n',
     ('tests.test_steps.Reread.test_the_item_is_read_again',)),
    # The approving act names a Pause the port could not read by the port's part (#688's seventh dry run, decision
    # 0192).
    ("a part is named for a snapshot's read alone", 'harness/shared.py',
     '    return "%s_%s_unreadable" % (stage, part) if part else "%s_unreadable" % stage',
     '    return "%s_%s_unreadable" % (stage, part) if part and stage == "snapshot" else "%s_unreadable" % stage', ('tests.test_approve.TheAct.test_each_fault_of_the_act_is_classed_as_the_design_classes_it',)),
    # Issue 880, the hand's part: a Run that writes code reads its commit, and its patch is handed over by its digest.
    ("a bundle names another artifact than the Result's", 'harness/shared.py',
     'BUNDLE_ARTIFACT = "result"',
     'BUNDLE_ARTIFACT = "bundle"', ('tests.test_harness.Engine.test_the_harness_fills_a_pushs_bundle', 'tests.test_apply.Bundle.test_what_run_hands_over_is_what_the_hold_reads')),
    ('the patch is handed over under another name', 'harness/shared.py',
     'BUNDLE_FILE = "bundle.patch"',
     'BUNDLE_FILE = "patch"', ('tests.test_harness.Engine.test_the_harness_fills_a_pushs_bundle', 'tests.test_harness.Job.test_the_job_hands_over_the_patch')),
    # Issue 856, the hand's first part: what a Task showed of its Findings is the Harness's to fill, bound by the Result's digest.
    ("a thread's text under its own id is a Finding's shown", 'harness/shared.py',
     'FINDING_TEXT = "finding:"',
     'FINDING_TEXT = "thread:"', ('tests.test_harness.Engine.test_the_harness_fills_shown',)),
]
