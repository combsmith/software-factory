# 0194. An act's read again of its own item asks when all of that item's Runs began, past the cap

Status: accepted. Decided for "A record's start is read from its job's started_at, trusted only once the job is in progress or ran (P-64)" (issue 724). It amends two rows of `docs/decisions/0193-when-a-run-began-is-read-from-its-jobs-trusted-only-once-a-job-is-in-progress-or-ran-and-kept-by-the-pass-records.md`. "The cap" holds for a read of every item's Runs, the pass's; for a read of one item's it no longer does. "What does not read it yet" foretold that the Harness's two reads would ask; one does. The rest of 0193 stands.

## Decision

| What | Decided | Because |
|---|---|---|
| A read of one item | The records port, handed an item (`on`), asks that item's Runs alone when they began. Another item's Runs are not asked, say nothing of a beginning, and do not make the read less than whole | A Run decides on its own item. Another item's jobs would spend its requests and could leave its read not whole for a Run it does not read |
| The cap | It does not count a read of one item: every Run of that item that is in progress or completed is asked, however many. A read of every item's Runs keeps the cap of 50 (`JOBS`), as 0193 rules | The pass works its cap off over passes, by what its records kept. A Run keeps nothing from one read to the next: under the cap, an item with more than 50 such Runs would never be read whole by an act again |
| What bounds it | The list itself: one request for each Run of the item among those the list gives, at most the 1,000 GitHub serves of a workflow's runs (`SERVED`) | On 2026-11-11 the Factory's repo held 27 Runs of every item together |
| Who asks so | `harness/reread.py`, the read again before an act, for the item its Run is on, with nothing kept (`began={}`) | The act decides again from what it reads, as the pass decided. Were the Kernel to read `began_at` before both ask, one reading would lack what the other has (0193) |
| Who does not | `harness/read.py`, the read that builds a Task, asks no job | It hands the Kernel no run record: it reads the list for what the Lenses' and the opening Runs recorded. Jobs that could not be read would leave its list not whole and refuse the Task, for a field nothing there reads |

## Why

Decision 0193 capped the jobs asked in one read and foretold the Harness's reads of their own item's Runs, without saying how the two meet. A cap on a reader that keeps nothing is no bound on its work: it is a point past which its item is deferred at every Run, for good, until a person steps in.

The exception fails closed where it fails: a Run of the item whose jobs cannot be read still leaves the read not whole, as 0193 rules.

## Boundaries

| Boundary | Check |
|---|---|
| The read again before an act asks the records port when its item's Runs began, with nothing kept, and for that item alone | `tests/test_steps.py::test_the_item_is_read_again`, `harness/reread.py`, `tools/mutants.py`, mutant: "apply's read again asks the records port no job", mutant: "apply's read again asks every item's jobs" |
| The read that builds a Task asks the records port no job | `tests/test_steps.py::test_the_reader_writes_the_tasks_inputs`, `harness/read.py`, `tools/mutants.py`, mutant: "the Run's read asks the records port for jobs" |
| A read of one item asks that item's Runs alone, told from another's by its repo and by its number; another item's Run, done or in progress, is not asked and leaves the read whole | `tests/test_adapters.py::test_a_read_of_one_items_runs_asks_them_alone_and_all_of_them`, `adapters/records.py`, `tools/mutants.py`, mutant: "another item's Runs are asked for their jobs", mutant: "another item's Run in progress leaves a read of one item not whole", mutant: "one item is told from another by its number alone", mutant: "one item is told from another by its repo alone" |
| A read of one item asks all of that item's Runs past the cap, in progress and completed alike, and is whole; the same list read for every item stops at the cap and is not whole | `tests/test_adapters.py::test_a_read_of_one_items_runs_asks_them_alone_and_all_of_them`, `adapters/records.py`, `tools/mutants.py`, mutant: "one item's Runs are asked no further than the cap", mutant: "one item's Runs in progress are asked no further than the cap", mutant: "one item's completed Runs are asked no further than the cap" |
| A Run of the item whose jobs cannot be read, past the cap too, has no beginning and leaves a read of one item not whole | `tests/test_adapters.py::test_a_read_of_one_items_runs_asks_them_alone_and_all_of_them`, `adapters/records.py`, `tools/mutants.py`, mutant: "a read of one item is whole whatever jobs of its Runs cannot be read" |
