"""The mutants of `Makefile`: tools/mutants.py runs them."""

TARGETS = ("Makefile",)
MUTANTS = [
    # Issue 907, decision 0240: the checks that hold a trust boundary are protected paths.
    ("make remakes the Makefile verify runs by from a file beside it", "Makefile", "Makefile: ;\n", "",
     ("tests.test_tools.Verify.test_make_reads_the_makefile_as_committed_and_remakes_it_from_nothing",)),
    ("the Makefile's own rule is a bare make's goal", "Makefile", ".PHONY: verify fast checks\nverify:\n",
     ".PHONY: verify fast checks\nMakefile: ;\nverify:\n",
     ("tests.test_tools.Verify.test_make_reads_the_makefile_as_committed_and_remakes_it_from_nothing",)),
    # Issue 438: the hooks run the checks alone, and a run that did not finish is no failure.
    ("make checks runs the whole verify", "Makefile",
     '\t$(PY) -I -S tools/verify.py --checks\n', '\t$(PY) -I -S tools/verify.py\n', ('tests.test_tools.Verify.test_make_fast_is_verify_without_the_seeded_simulation',)),
    ("make checks does nothing", "Makefile",
     '\t$(PY) -I -S tools/verify.py --checks\n', '\t@true\n', ('tests.test_tools.Verify.test_make_fast_is_verify_without_the_seeded_simulation',)),
    # Issue 1050: verify runs isolated, the repo's top after the standard library.
    ("make verify puts the repo's top ahead of the standard library", "Makefile",
     "\nverify:\n\t$(PY) -I -S tools/verify.py\n", "\nverify:\n\t$(PY) -m tools.verify\n",
     ("tests.test_tools.Verify.test_a_file_at_the_top_named_as_a_standard_module_is_not_imported_by_the_checks",)),
]
