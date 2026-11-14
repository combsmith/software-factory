# 0196. The pass asks when a Run began only of the open pull requests' Runs

Status: accepted. The Factory Builder's ruling of 2026-11-11 on "A record's start is read from its job's started_at, trusted only once the job is in progress or ran (P-64)" (issue 724). It amends two rows of `docs/decisions/0193-when-a-run-began-is-read-from-its-jobs-trusted-only-once-a-job-is-in-progress-or-ran-and-kept-by-the-pass-records.md`. "What is asked" said each Run in progress or completed; for the pass it is now each such Run of an open pull request. "The cap" gave a count of the Factory's Runs that was wrong, and is corrected here. The rest of 0193 stands.

## Decision

| What | Decided | Because |
|---|---|---|
| What the pass asks | The jobs of a Run in progress or completed whose item is an open pull request of the home repo, and of no other Run. The entry hands the records port those items (`of`). A list with no item in it asks no Run. A caller that hands no list asks every Run, as 0193 rules | The list keeps every Run for 90 days, and an item that has closed is not decided again. A beginning is for the rule that dates an approval, which reads only the records of the item it decides |
| Another item's Run | Not asked. It says what the records before kept of it, if anything, and no more. It leaves the list whole | Nothing reads its beginning. Were it to leave the list not whole, the list's history would defer the pass's live work |
| The cap | Unchanged: 50 Runs asked in one read (`JOBS`), now counted among the open pull requests' Runs. One past it, or whose jobs cannot be read, still leaves the list not whole | The cap bounds one pass's requests. This bounds what there is to ask |
| The order of the reads | The entry lists the open pull requests, then reads the run records. A list of open pull requests not read whole stops the pass before the run records are read | The port must be handed the items before it asks |
| The count 0193 gave | 0193's "27" was a miscount. On 2026-11-11 GitHub listed 98 dispatched Runs on main for the two Role workflows, the oldest of 2026-11-09, about 40 more a day. 47 of them were of the 11 pull requests then open | Counted from the two lists the port reads, and each Run's item from its name |
| The cold start | With nothing kept, N Runs to ask take ceil(N/50) passes, and every item is deferred in each but the last. Asking every Run, N was 98 that day and would pass 1,000 in a month. Asking the open pull requests' Runs, N was 47: one pass | A cold start is the first pass that asks, or two pass records in a row that list no Run. It fails closed either way; this decides how long |
| Issues | Not asked: the pass decides no issue yet. When the issue Lifecycle's port is built, its open issues join the items handed | A rule that waits on a part says so |

## Why

Decision 0193 capped the asking and reasoned from 27 Runs. The list is the Factory's history, not its work: it grows by every Run of every pull request, merged or closed, for 90 days. A cap on history turns each cold start into hours of passes that defer everything, and an outage that loses two records in a row starts one.

What a pass decides is the open pull requests. Their Runs are what it has a use for, and they are few for as long as pull requests merge.

## Boundaries

| Boundary | Check |
|---|---|
| The port asks the jobs only of the Runs of the items given, each told by its repo, its type and its number; another item's Run is not asked, says what was kept of it, and leaves the list whole; a list with no item in it asks no Run, and no list asks every Run | `tests/test_adapters.py::test_the_asking_is_bounded_to_the_items_given`, `adapters/records.py`, `tools/mutants.py`, mutant: "a Run of an item not given is asked for its jobs", mutant: "a Run of an item not given leaves the list not whole", mutant: "a Run of an item not given says nothing of what was kept", mutant: "no item given asks every Run", mutant: "an item is given by its number alone", mutant: "an item is given by its repo alone", mutant: "an item is given by its repo and number, whatever its type" |
| The cap holds among the items given, and one of their Runs whose jobs cannot be read leaves the list not whole | `tests/test_adapters.py::test_the_asking_is_bounded_to_the_items_given`, `adapters/records.py`, `tools/mutants.py`, mutant: "the items given are asked past the cap", mutant: "a read of the items given is whole whatever jobs of their Runs cannot be read" |
| The entry hands the records port the open pull requests it listed, as pull requests of the home repo | `tests/test_controller.py::test_the_entry_gathers_what_reconciliation_reads`, `controller/__main__.py`, `tools/mutants.py`, mutant: "the entry bounds the asking to no item", mutant: "the entry asks the jobs of every Run", mutant: "the entry bounds the asking to issues" |
| A list of open pull requests not read whole stops the pass before the run records are read | `tests/test_controller.py::test_what_the_entry_cannot_read_writes_nothing`, `controller/__main__.py`, `tools/mutants.py`, mutant: "the run records are read though the open pull requests were not read whole" |
| When the pass decides issues, its open issues join the items the entry hands the records port, so that their Runs' jobs are asked | waiting on `adapters/linked.py`, the issues port's last part, and the pass's wiring after it |
