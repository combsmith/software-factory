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
     '\t$(PY) -m tools.verify --checks\n', '\t$(PY) -m tools.verify\n', ('tests.test_tools.Verify.test_make_fast_is_verify_without_the_seeded_simulation',)),
    ("make checks does nothing", "Makefile",
     '\t$(PY) -m tools.verify --checks\n', '\t@true\n', ('tests.test_tools.Verify.test_make_fast_is_verify_without_the_seeded_simulation',)),
]
