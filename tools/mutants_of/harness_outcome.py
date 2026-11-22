"""The mutants of `harness/outcome.py`: tools/mutants.py runs them."""

TARGETS = ("harness/outcome.py",)
MUTANTS = [
    # Muse's read of #194's PR 3.
    ("another Run's outcome is kept", 'harness/outcome.py',
     ' or (kept["run"], kept["release"]) != (parts["run"], release)',
     '', ('tests.test_steps.Apply.test_the_last_step_leaves_the_outcome',)),
    ('a Run whose apply left nothing leaves nothing', 'harness/outcome.py',
     '    except Stop:\n        kept = None\n',
     '    except Stop:\n        raise\n', ('tests.test_steps.Apply.test_the_last_step_leaves_the_outcome',)),
    # The Claude review of #196 PR 2b-1.
    ('an outcome that names a fault concludes the Run a success', 'harness/outcome.py',
     '    if kept["outcome"] is not None:\n        raise Stop(kept["reason"] or kept["outcome"])\n',
     '', ('tests.test_steps.Apply.test_the_last_step_leaves_the_outcome',)),
    # #196 PR 2b-2: the Release a step runs as, read from its checkout's one Release tag.
    ('the outcome is of a Release it did not read', 'harness/outcome.py',
     '    release = steps.release()',
     '    release = "factory/v9.9.9"', ('tests.test_steps.Apply.test_the_last_step_leaves_the_outcome',)),
    # A Run on another Release than its pass's (#197's ruling 8).
    ("the reader's outcome of a moved Run is not kept", 'harness/outcome.py',
     '        kept = moved\n',
     '        pass\n', ('tests.test_steps.Reader.test_a_run_on_another_release_than_its_pass_builds_no_task',)),
    ("another Run's or Release's moved outcome is kept", 'harness/outcome.py',
     ' and (moved["run"], moved["release"]) == (parts["run"], release) \\\n            and',
     ' and', ('tests.test_steps.Reader.test_a_run_on_another_release_than_its_pass_builds_no_task',)),
    ('any outcome the reader left is kept', 'harness/outcome.py',
     ' \\\n            and (moved["outcome"], moved["reason"]) == MOVED:',
     ':', ('tests.test_steps.Reader.test_a_run_on_another_release_than_its_pass_builds_no_task',)),
    ("the reader's outcome is not read in the workflow's form", 'harness/outcome.py',
     '    argv = steps.given(argv, environ, ("NAME",), ("applied", "outcome", "reader-outcome"))',
     '    argv = steps.given(argv, environ, ("NAME",), ("applied", "outcome"))', ('tests.test_steps.Reader.test_a_run_on_another_release_than_its_pass_builds_no_task',)),
]
