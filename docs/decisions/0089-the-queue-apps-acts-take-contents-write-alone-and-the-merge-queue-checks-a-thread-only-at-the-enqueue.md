# 0089. The queue App's acts take contents: write alone, and the merge queue checks a thread only at the enqueue

Status: accepted. Window 3, run on 2026-10-29 for "A narrow queue App, combsmith-sf-queue, enqueues and dequeues with contents and pull-request write alone (P-2)" (issue 381) and "A Lens's thread is resolved by a Kernel act the queue App carries out, on that Lens's accepted ruling, never by the Lens's own App" (issue 389), under the
orchestrator's ruling (a) of that day. It adds to decisions 0081 and 0085, whose queue fixtures it extends.

## Decision

| What | Decided | Because |
|---|---|---|
| The queue App's least permission | Its enqueue, dequeue and resolve each take `contents: write` alone, with `metadata: read`; `pull_requests: write` serves none, and the Maintainer removed it from the App | `trials/P-2.queue-app.json` and `trials/P-5.queue.json`: each act, narrowed so, did what it was asked, and every refusal was of the pull request's state |
| The merge queue and an open thread | Under a ruleset that requires threads resolved, the queue refuses an enqueue with a thread open, but merges a pull request that gains a thread while it waits. The Kernel cannot leave that to the queue: a thread opened after the enqueue must lead it to dequeue | `trials/P-2.queue-app.json`: on the canary, a pull request merged with a thread opened 8 seconds after its enqueue still open |
| Who a merge names | The merge names whoever put the pull request in the queue: the queue App for its enqueue, the machine user for a browser's "Merge when ready" | `trials/P-2.queue-app.json`, on two canary pull requests |
| P-5 with the queue App | The resolver reads back as the queue App, a User by its type, with its database id, which the threads port reads | `trials/P-5.queue.json` |

## Why

Ruling (a) asked whether the queue's three acts need more than `contents: write` before the App was recorded in
the data, and the resolve act's issue owed three trials before the Kernel's resolve rests on the queue App.

## Boundaries

| Boundary | Check |
|---|---|
| The window's refusals are placed | `tests/test_adapters.py::test_a_recorded_refusal_is_no_answer` |
| Each write is on a canary node a read answered | `tools/check_trials.py` |
