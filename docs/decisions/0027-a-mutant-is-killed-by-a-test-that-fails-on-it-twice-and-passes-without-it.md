# 0027. A mutant is killed by a test that fails on it twice and passes without it

Status: accepted. Ruled by the Solution Architect, delegated, for
"Mutation run: a mutant is killed only by a test that fails because of it" (issue 147); the
Maintainer may overturn it in review.

## Decision

A run of the suite on a mutant stops at its first failure, as before. That failure kills the mutant
only once it is confirmed: `tools/mutants.py` reads the one test that failed from unittest's output,
runs that test alone on the mutant, where it must fail again, and alone on the unbroken code, where
it must pass. The unbroken code is a second copy, made as the mutant's is, with no `.git` and under
the system's temporary directory: a test that fails in any copy and passes in the checkout fails
there too, so a change cannot make its own mutants look killed that way. If either run disagrees, the failure is unconfirmed, and the suite runs once more on
the mutant: a pass is `SURVIVED`, a confirmed failure is `killed`, and a second unconfirmed failure
is `FLAKY`, which names the test and whether it passed again on the mutant or failed on the unbroken
code too. `FLAKY` is not counted as killed, so it fails the run as an `ERROR` does. The tests a
mutant names first still run first, only for speed.

- The test is read from the line unittest prints under its rule of `=`, in either form: the method
  and its class, as 3.9 and 3.10 print it, or the method and its whole id, as 3.11 and later do,
  with any subtest after it. A failure in `setUpClass` names the class, which then runs alone. A
  line it cannot read, or two tests where one stopped the run, is an `ERROR`.
- The suite is discovered from the top of the copy, as `tools/verify.py` discovers it, so that a
  test's id is its dotted path, the form the tests a mutant names are written in and the form that
  runs alone.
- A timeout, on any run, a confirmation's among them, stays an `ERROR`: never a kill, never `FLAKY`.
- A test whose verdict rests on the wall clock is marked `@wall_clock`, from `tests/support.py`. It
  is skipped when mutating, as a test marked `@pending` is, and runs in `make verify` with its
  margins as they are: four in `tests/test_hooks.py` and two in `tests/test_tools.py`. A test that
  only spends a budget of nothing is not marked, since load only makes a spent budget more certain.

The unbroken suite's first run stays as it is: if it fails, the check stops before any mutant.

## Why

A failing test counted as a kill, whatever made it fail. On a laptop with a load average near 30,
four mutants of code that had become dead were reported killed by a test that failed under load,
while CI's shards reported them surviving: four rules nothing checked, passed as checked. Only a
run on each side tells three failures apart: one the mutant causes, which fails again on it and
passes without it; one already broken, which fails without it too; and one caused by load, which
passes when run again. The second run of the suite gives a failure caused by load one more chance
to be the mutant's before the mutant is called anything.

`FLAKY` fails the run. Reporting it and passing would let through a rule nobody showed a test
notices, which is the failure this decision exists to stop, in a quieter form. A timeout is not
read as `FLAKY`: 600 seconds is ten to thirty times a whole run, so a timeout means a hang, and a
rule only a hang shows needs a test that fails.

No mutant touches a hook's time budget, so skipping the tests timed by the wall clock loses no
kill; a test holds that each such test carries the mark.

Not taken: counting only the tests a mutant names, which most mutants do not have and which would
leave a rule another test holds unseen; and running without `-f`, to read every failure, which
costs a whole run on every mutant and still cannot tell a failure caused by load from the mutant's.

The cost is two runs of one test a mutant, about 35 seconds a shard against a run of about ten
minutes. Left for later: `Budget` in `tools/hooks/protected.py` and the clock in
`tools/hooks/identity.py` are to take a clock given them, so that their tests need no mark and their
budgets get mutants; and a test that kills only when the whole suite runs, if one ever shows as
`FLAKY`, is to be given its own setup.

## Boundaries

| Boundary | Check |
|---|---|
| A failure kills a mutant once its test fails again alone on the mutant and passes alone on the unbroken code | `tests/test_tools.py::test_a_failure_the_mutant_causes_kills_it` |
| A mutant whose only failure is an unrelated test, which passes when run again, is `SURVIVED` | `tests/test_tools.py::test_a_mutant_whose_only_failure_is_unrelated_survives` |
| A test that fails only in a copy, with no `.git`, kills nothing: the unbroken code it passes on is a copy too | `tests/test_tools.py::test_a_test_that_fails_only_in_a_copy_kills_nothing` |
| A test that fails alone on the unbroken code too kills nothing | `tests/test_tools.py::test_a_test_that_fails_on_the_unbroken_code_too_kills_nothing` |
| Two unconfirmed failures are `FLAKY`, which is not counted as killed and fails the run; a confirmation that times out is an `ERROR` | `tests/test_tools.py::test_a_failure_that_is_not_the_mutants_twice_is_flaky_and_fails_the_check` |
| The test is read from the line each Python prints under unittest's rule, a subtest's and `setUpClass`'s among them; a line not read is an `ERROR` | `tests/test_tools.py::test_the_failing_test_is_read_from_the_line_each_python_prints` |
| A test named to run alone runs alone, in a suite of many | `tests/test_tools.py::test_the_tests_a_mutant_names_run_first_and_the_whole_suite_after_them` |
| Exactly the tests that read the clock or sleep, however `time` is imported, carry `@wall_clock`, which skips it when mutating and leaves it as it is otherwise | `tests/test_tools.py::test_every_test_timed_by_the_wall_clock_is_marked_and_skipped_when_mutating` |
| Each rule above has a mutant that a test kills | `tools/mutants.py` |
