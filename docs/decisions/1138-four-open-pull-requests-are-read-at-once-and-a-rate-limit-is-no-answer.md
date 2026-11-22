# 1138. Four open pull requests are read at once, and a rate limit is no answer

Status: accepted. The Solution Architect's ruling of 2026-11-22 on "controller: reconciliation reads grow until a pass runs out of time" (issue 1025).

## Decision

| What | Decided | Because |
|---|---|---|
| What is read at once | The open pull requests' snapshots alone, in `controller/__main__.py`, each whole in a thread of its own, its reads one after another as before, so the read-twice check of a pull request that moved still holds. All else the pass reads, the effects and the write's bound stay one at a time; `controller/pass_.py` is unchanged | On 2026-11-21 the snapshots took a median 106 seconds, 55% of a pass |
| How many | A fixed pool of four threads from the standard library, `main`'s default; each thread times its own reads, added up after in the listed order | Four takes most of the wait off with few requests in flight against a token's limit |
| The order | The entries are kept in the listed order whatever order their reads end in, so the record is the one a pass reading them one at a time writes | A record must not depend on timing (decision 0002) |
| A rate limit | A 429, or a 403 with no request left or a time to wait, is GitHub not answering, and that request is not sent again. It leaves its pull request out as `facts_unanswered` whichever of the snapshot's reads met it, its account reader's among them, even where the part that asked read on. Once one is seen, no snapshot begins in a thread: each looks as it begins, and those that did not begin are read one at a time in the pass's own thread once the threads end | No retry loop: the pass has a budget of minutes, and the next pass reads it again |
| What the threads share | The account reader asks a login's permission once, whatever thread asks first, and every thread reads the one answer kept. Each snapshot has its own copy of it, keeping the same answers and asking by that snapshot's transport | Two threads asking together could keep two answers; a rate limit a permission read meets is its snapshot's |
| A recorded exchange | `read` and `one_pass` read one at a time unless given more, and a test's replay of recorded exchanges reads one at a time | Answers recorded in order cannot be handed to threads in an order no one chose |
| The carry's line | The decide stage's line counts the issues owed and left and the hands' approvals too, in the log alone | Part (3) of the ruling: these carries grow with the window too |
| Rejected and deferred | Skipping a pull request whose `updated_at` has not changed: rejected, a merge state changes under it (P-40). Carrying the reads of pull requests that left: deferred until `seen_gone`'s 90th percentile passes about 60 seconds | The ruling |

## Why

The snapshots are most of a pass and grow with the queue; each is independent of the others, so reading a few at once shortens the pass and changes nothing the Kernel decides.

## Boundaries

| Boundary | Check |
|---|---|
| By `main`'s default up to four snapshots are read at once and the record is the one read one at a time writes, in the listed order; a rate limit's answer to a snapshot's read or its account reader's leaves that pull request alone out, sent once, even where the part read on, and one not begun by then begins in the pass's own thread after the threads end | `tests/test_controller.py::test_the_open_pull_requests_are_read_four_at_once_and_kept_in_the_listed_order`, `controller/__main__.py`, mutant: "the open pull requests are read one at a time", mutant: "a fifth thread reads a snapshot at once", mutant: "a snapshot is kept in the order its read ends", mutant: "the entry reads one snapshot at a time by default", mutant: "the pool is one", mutant: "the pool is three", mutant: "a rate limit's answer is an answer", mutant: "a part that read on past a rate limit keeps its pull request", mutant: "a rate limit leaves out every snapshot read at once", mutant: "a snapshot's account reader asks past the rate limit", mutant: "a rate limit is told to no other snapshot", mutant: "a snapshot begins in a thread of its own after a rate limit is seen" |
| A rate limit is a 429, or a 403 with no request left or a time to wait; any other answer, or none, is not | `tests/test_controller.py::test_a_rate_limit_is_a_429_or_a_403_with_no_request_left_or_a_time_to_wait`, `controller/__main__.py`, mutant: "a 429 is no rate limit", mutant: "a 403 with no request left is no rate limit", mutant: "a 403 with a time to wait is no rate limit", mutant: "another refusal with no request left is a rate limit", mutant: "any 403 is a rate limit" |
| A login two threads ask together, by a reader and its copy, is asked once, the second waiting on the first, both reading the one answer; a copy of the reader keeps its answers and asks by its own transport | `tests/test_adapters.py::test_a_permission_is_asked_once_however_many_threads_ask_it`, `adapters/timeline.py`, mutant: "a thread that finds a login asked asks it again", mutant: "a thread reads a login's permission before the first ask ends", mutant: "a reader asking by another transport asks by the first", mutant: "a reader asking by another transport keeps answers of its own", mutant: "a copy of the reader asks what another has under way" |
| The decide stage's line counts the issues owed and left and the hands' approvals; the snapshots' reads are timed though read at once | `tests/test_controller.py::test_each_stage_of_a_pass_is_timed_in_the_log_alone_and_times_no_read_differently`, `controller/__main__.py`, mutant: "the carry's line counts no issue owed", mutant: "the carry's line counts no issue left", mutant: "the carry's line counts no hand's thread", mutant: "the open pull requests' reads are not timed" |
