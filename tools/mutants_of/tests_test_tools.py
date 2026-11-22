"""The mutants of `tests/test_tools.py`: tools/mutants.py runs them."""

TARGETS = ("tests/test_tools.py",)
MUTANTS = [
    # Issue 342: an opening Run records the pull request it opened by the number read back, on its own branch.
    ("a repo copy is kept to the run's end", 'tests/test_tools.py',
     '        case.addCleanup(shutil.rmtree, str(made), True)\n', '        pass\n', ('tests.test_tools.Copies.test_a_copy_of_the_repo_is_removed_when_the_test_that_made_it_ends',)),
    # Issue 458: a signal becomes a script's exit, the same in each.
    ('the signal tests use a shell that runs an EXIT trap all the same', 'tests/test_tools.py',
     'SIGNAL_SHELL = shutil.which("dash") or "sh"\n', 'SIGNAL_SHELL = shutil.which("bash") or "sh"\n', ('tests.test_tools.SignalTraps.test_the_signal_tests_shell_leaves_an_exit_trap_unrun',)),
    # Issue 484: one noisy measure is not growth.
    ('a reading in CPU is measured once', 'tests/test_tools.py',
     'spent, _ = support.measured(lambda n: read(unit * n), size, cpu_problem)', 'spent, _ = support.measured(lambda n: read(unit * n), size, lambda each: "")', ('tests.test_tools.CpuReadings.test_one_noisy_measure_of_a_reading_is_measured_again',)),
    ('a reading in CPU has no limit', 'tests/test_tools.py',
     '    if spent[-1].cpu >= 0.5:\n', '    if False:\n', ('tests.test_tools.CpuReadings.test_one_noisy_measure_of_a_reading_is_measured_again',)),
    ('a reading in CPU may grow', 'tests/test_tools.py',
     '        return "spent %.2f s of CPU at its size, past half a second" % spent[-1].cpu\n    return support.faster_than_linear(*spent)\n', '        return "spent %.2f s of CPU at its size, past half a second" % spent[-1].cpu\n    return ""\n', ('tests.test_tools.CpuReadings.test_one_noisy_measure_of_a_reading_is_measured_again',)),
]
