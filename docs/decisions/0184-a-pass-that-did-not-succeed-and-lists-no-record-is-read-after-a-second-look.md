# 0184. A pass that did not succeed and lists no record is read, after a second look

Status: accepted. The Factory Builder's ruling of 2026-11-10 on the `reconciliation_unreadable` alert of "Factory alerts" (issue 709). It amends one row of `docs/decisions/0112-a-pass-gathers-what-reconciliation-reads-and-carries-what-it-has-read.md`: "One that failed and lists none may be yet to, so it too is read again, without being short" held for a Run and for a pass alike; for a pass it no longer does. What 0112 says of a Run's `applied/1` is unchanged.

## Decision

| What | Decided | Because |
|---|---|---|
| A pass that did not succeed and lists no `written` | It is looked at once more in the same pass. Listing none again, it is read: it goes into what the record carries with no `written/1`, and no later pass asks of it | A run that is completed uploads nothing more, so "may be yet to" covered only a lag in GitHub's list of its artifacts. Never read, each such pass was asked of again by every pass for the whole window, and each asking spent one of the 50 a pass reads (`READS`) |
| The wait | One wait of 5 seconds (`WAIT`, as the records port's in decision 0036) before the second looks, however many there are; none when no pass is looked at again. Every first look comes before it | The wait is for the list to settle, and one settles them all. A pass with nothing to look at again is no slower |
| What the second look finds | A record: it is read as any record is, held to `written/1` and to a record's bound. None, or one past its retention: the pass is read, with nothing recorded. A list or a record that cannot be read, or a record that is no `written/1`: the pass is not read, a later pass looks again, and what was read is short | The second look is held to everything the first is; only "lists none" changes its meaning |
| The bound | `most` bounds the first looks, as before. The second looks are at most as many again, and each is one request unless a record has appeared | The 50 was set inside the step's limit of 6 minutes; one wait and at most 50 more list requests stay inside it |
| A pass that succeeded and lists none | Unchanged: short at its one look, never looked at twice, read again by a later pass | A pass that succeeded uploaded a record, so none listed is lag or a deletion, and nothing was recorded that can stand for it |
| A run not completed | Unchanged: it is no pass yet, nothing is asked of it, and the pass after it has ended reads it | It is the one case that may yet record |
| A write such a pass made | Is matched to no record, so `write_unmatched` is raised, at once and for as long as the write is in the window | Reconciliation fails closed where it always did: a pass read as having recorded nothing vouches for no write. Should the list lag past both looks, a recorded write alarms as unmatched; it is never passed in silence |
| A Run that did not succeed and lists no `applied` | Not decided here: `adapters/applied.py`'s `effects` still reads it again at every pass, and counts it toward its own 50 | The ruling was on the passes, which is where the alert was raised; the same shape for Runs is left to its own ruling |

## Why

The poller keeps one run going and one waiting, and cancels the one that waits when another is queued. A cancelled run records nothing. On 2026-11-10 the window of 30 hours held 50 cancelled passes and 1 that failed, against 180 that succeeded. None of the 51 was ever counted read, so from the 03:06Z pass on every pass spent its 50 reads on them, found more than 50 to read, and raised `reconciliation_unreadable`, with nothing unread that could be read. The alert would have stood until fewer than about 49 such passes fell inside the window.

Reading them is safe because nothing is taken on trust: a pass read with no record adds no key and no credit, so any write it made stays unmatched and alarms.

## Boundaries

| Boundary | Check |
|---|---|
| A pass that did not succeed and lists none is read after a second look, one wait before them all and none with none to look at again; a record the second look lists is read; a second look that cannot be read leaves the pass unread and what was read short; one that succeeded is never looked at twice | `tests/test_adapters.py::test_a_pass_that_did_not_succeed_and_lists_none_is_read_after_a_second_look`, `adapters/passes.py`, `tools/mutants.py`, mutant: "a pass that lists none is read at its first look", mutant: "the second look does not wait", mutant: "the second look waits no time", mutant: "a pass waits with none to look at again", mutant: "each second look waits", mutant: "a second look that cannot be read counts as read", mutant: "a second look that cannot be read is whole", mutant: "a record the second look lists is not read" |
| More such passes than a pass reads are read whole by the next pass, and as many as it reads by one | `tests/test_adapters.py::test_more_passes_that_list_none_than_a_pass_reads_are_read_whole_by_the_next`, `adapters/passes.py`, `tools/mutants.py`, mutant: "a pass that did not succeed and lists none is never read" |
| A run not completed is not looked at, is not read, and leaves what was read whole | `tests/test_adapters.py::test_a_pass_still_running_is_not_looked_at_and_may_yet_record`, `adapters/passes.py`, `tools/mutants.py`, mutant: "a pass still running is looked at" |
| A write by a pass that failed and recorded nothing is unmatched, and the reconciliation is not short; one it recorded, listed at the second look, is matched | `tests/test_adapters.py::test_a_write_by_a_pass_that_failed_and_recorded_nothing_is_unmatched_not_short`, `adapters/passes.py`, `tools/mutants.py`, mutant: "a pass that lists none at its second look is short" |
| One past its retention is read at its one look; one that succeeded and lists none is short | `tests/test_adapters.py::test_each_pass_in_the_window_is_read_once_and_what_cannot_be_read_is_read_again`, `adapters/passes.py`, `tools/mutants.py`, mutant: "a pass past its retention is looked at again", mutant: "a pass that succeeded and lists none wrote nothing" |
