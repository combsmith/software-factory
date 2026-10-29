# 0083. A mutant run's baseline runs the tests its own mutants name, method by method among its workers, and a slow one is not a red one

Status: accepted. The Factory Builder's ruling of 2026-10-28, which the Maintainer may overturn in review, on issue 396, "A mutant shard's baseline runs what its own mutants name, so it no longer outgrows the 600 s a run is given". It extends `docs/decisions/0027-a-mutant-is-killed-by-a-test-that-fails-on-it-twice-and-passes-without-it.md`.

## Decision

| What | Decided | Because |
|---|---|---|
| What the baseline runs | Before anything is broken, `tools/mutants.py` runs the tests the run's own mutants name: a shard's, a filtered run's, or every mutant's at a desk. Each test runs once. A list that names no test runs the whole suite, as before | The whole suite outgrew the 600 s a run is given on a CI runner: five of eight shards in one merge group ran out of time before any mutant was tested. The whole suite still runs, mutant by mutant, after any mutant's named tests pass |
| How it is run | A child process reads the names in the tree the baseline runs in, method by method, with unittest's own loader. They are dealt out in turn among the run's workers, and the parts run at once. A name read as no test, or as any id that is not a test under `tests/`, is kept whole, for its own run to find. Where the tree cannot be read, every name is kept whole | Mutants name whole classes and modules, `tests.test_tools.Trials` among them. Read only by name, those held one part for most of the time; read method by method, they are shared. An id is never passed to unittest as one of its options |
| The ceiling | Unchanged: each part is one run, held to `TIMEOUT`, 600 s, as every run is. It is not raised | The room under it comes from the workers, not from the shard. Mutants name whole classes, and the shards share them, so each shard names 61 to 67 per cent of the suite's tests. Its baseline grows nearly as the suite does, divided among the workers. On a desk, shard 0's took 132 to 150 s, its parts 83 to 144 s, where the whole suite took 523 s: about a quarter of the ceiling, on four workers |
| A red baseline | A part in which a test failed stops the run before any mutant is broken, as before. This holds whichever part it is, whatever else was slow, and when the part ran out of time after the failure | A mutant cannot be told from a test that is already red |
| A slow baseline | A part that only ran out of time, with no test failed among those that ran, stops the run too. It says that the named tests took longer than 600 s, and that none that ran failed. It is never read as a red test | The two need different fixes: a red test is mended; a slow baseline needs narrower tests named, or more workers |
| What a kill rests on | Unchanged: a kill is confirmed by `confirm`, which runs the test that failed on the mutant again and on the unbroken code (0027). The baseline only decides whether the run goes on. A test red on the unbroken code that no mutant of a shard names is not run by that shard's baseline. A mutant that reaches it in the whole suite ends FLAKY, which fails the shard | Narrowing the baseline makes no kill easier to claim |
| Accepted | A mutant whose named tests pass, whether it survives or is killed by a test it does not name, still runs the whole suite after them, held to the same 600 s. Once the suite passes 600 s on a runner, such a mutant is an ERROR that says the run took longer. Both fail the shard. Which mutants rely on the whole suite is not recorded: a shard that has one will show it as that ERROR | Issue 396's ask was the baseline. Issue 398, "Mutant shards scale with their count: a disjoint share of the named tests for each baseline, and a survivor's whole-suite run kept under the limit", files both fixes, since the whole suite takes 523 s on a desk and CI's runners are slower |

## Why

A mutant run first shows the tests pass on the unbroken code, so that a failing test can be read as the mutant's. That run was the whole suite, under the same ceiling as every run, and the suite grew with every fixture. On 2026-10-28 the baseline ran out of time three times, ejecting a pull request from the queue. Its message said the tests failed, which they had not.

## Boundaries

| Boundary | Check |
|---|---|
| The baseline runs the tests the run's mutants name, method by method as read in its tree, each once, dealt among its workers. A name read as no test, an id not under `tests/`, and a tree that cannot be read keep the names whole. A list naming none runs the whole suite | `tests/test_tools.py::test_the_baseline_runs_the_tests_its_mutants_name_in_parts_never_the_whole_suite` |
| A part that only ran out of time says so and stops the run. A part with a failed test stops it as red, whichever part it is, whatever else was slow, and though it then ran out of time. Neither breaks a mutant | `tests/test_tools.py::test_a_baseline_that_is_only_slow_says_so_and_one_that_is_red_stops_the_shard` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
