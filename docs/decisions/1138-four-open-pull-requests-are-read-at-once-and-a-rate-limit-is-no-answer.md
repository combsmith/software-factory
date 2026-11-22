# 1138. Four open pull requests are read at once, and a rate limit is no answer

Status: accepted. The Solution Architect's ruling of 2026-11-22 on the stage timings of "controller: reconciliation reads grow until a pass runs out of time" (issue 1025), as the Factory Builder relayed it.

## Decision

| What | Decided | Because |
|---|---|---|
| What is read at once | The open pull requests' snapshots alone, in `controller/__main__.py`: each snapshot is read whole in a thread of its own, its reads one after another as before, so the read-twice check of a pull request that moved still holds. Everything else the pass reads, the writes seen, the effects and the write's bound stay one at a time, and `controller/pass_.py` is unchanged | Over 24 hours of passes on 2026-11-21 the open pull requests' snapshots took a median 106 seconds, 55% of a pass, about 5.6 seconds each, read one at a time |
| How many | A fixed pool of four threads from the standard library; each thread times its own reads, and they are added up after, in the listed order | Four takes most of the wait off with few requests in flight at once, against a token's limit |
| The order | The entries are kept in the order the pull requests were listed, whatever order their reads end in, so the record is the one a pass reading them one at a time writes | A record must not depend on timing (decision 0002) |
| A rate limit | An answer of 429, or a 403 with no request left or a time to wait, is read as GitHub not answering: that pull request is left out as `facts_unanswered`, as any snapshot GitHub did not answer, and is not asked again. Once one is seen, the snapshots not yet begun are read one at a time in the pass's own thread | No retry loop: the pass has a budget of minutes, and the next pass reads it again |
| What the threads share | The reader of who an account is asks GitHub for a login's permission once, whatever thread asks first, and every thread reads the one answer kept | Two threads asking together could keep two answers, and a later snapshot would read whichever came last |
| A recorded exchange | `main` reads four at once; `read` and `one_pass` read one at a time unless given more, and a test's replay of recorded exchanges, whose answers come in order, reads one at a time | Answers recorded in order cannot be handed to threads in an order no one chose |
| Rejected and deferred | Skipping a pull request whose `updated_at` has not changed is rejected: a merge state changes under the same `updated_at` (P-40). Carrying the reads of pull requests that left is deferred, unless `seen_gone`'s 90th percentile passes about 60 seconds | The Solution Architect's ruling |

## Why

Read one at a time, the open pull requests' snapshots are most of a pass, and they grow with the queue. Each snapshot is independent of the others, so reading a few at once shortens the pass, and nothing the Kernel decides changes.

## Boundaries

| Boundary | Check |
|---|---|
| Up to four snapshots are read at once, each in its own thread, and the record is the one a pass reading them one at a time writes, its entries in the listed order whatever order the reads end in; a rate limit's answer leaves that pull request out as unanswered, and the snapshots not yet begun are read one at a time in the pass's own thread | `tests/test_controller.py::test_the_open_pull_requests_are_read_four_at_once_and_kept_in_the_listed_order`, `controller/__main__.py`, mutant: "the open pull requests are read one at a time", mutant: "more open pull requests than the pool are read at once", mutant: "a snapshot is kept in the order its read ends", mutant: "a rate limit leaves the snapshots left read at once", mutant: "a rate limit's answer is an answer" |
| A rate limit is a 429, or a 403 with no request left or a time to wait; any other answer, or one that is no answer, is none | `tests/test_controller.py::test_a_rate_limit_is_a_429_or_a_403_with_no_request_left_or_a_time_to_wait`, `controller/__main__.py`, mutant: "a 429 is no rate limit", mutant: "a 403 with no request left is no rate limit", mutant: "a 403 with a time to wait is no rate limit", mutant: "another refusal with no request left is a rate limit", mutant: "any 403 is a rate limit" |
| A login two threads ask together is asked once, and both read the one answer kept | `tests/test_adapters.py::test_a_permission_is_asked_once_however_many_threads_ask_it`, `adapters/timeline.py`, mutant: "a thread that finds a login asked asks it again", mutant: "a thread reads a login's permission before the first ask ends" |
