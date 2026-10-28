# 0081. A fixture records a write on a node of the canary, and P-2 names what the queue takes

Status: accepted. The second machine-user window's first fixtures, under the orchestrator's rulings of 2026-10-28 on
the split and on the write exception, and the Maintainer's choice of a queue App the same day. It adds to decision 0035,
whose fixtures read the canary alone.

## Decision

| What | Decided | Because |
|---|---|---|
| A recorded write | `tools/check_trials.py` admits a GraphQL write in a fixture of the canary only when it is one of `WRITES` (enqueue, dequeue, auto-merge, convert to draft, resolve a thread), in its exact shape, on one node by its one `id`; that node is one a read of the canary alone in the same fixture answered, and its id decodes to the canary's repository, `CANARY_ID`. A merge method rides on auto-merge alone | The window's answers are writes and their refusals; a node names no repo, so it is held by the read that answered it and by the repository its id names |
| P-2's least permissions | `trials/P-2.least.json`: the pr-review App, with every permission it holds, is refused both the enqueue and the dequeue; an App enters and leaves the queue only with `contents: write`; the Controller reads a queued pull request with `metadata: read` alone. Its verdict is fail, as its condition names the pr-review App | A reviewer's App holds no content write, so the queue's writes go to an App of their own |
| The queue's needs | `read:facts.queue` maps to `metadata: read`, which the Controller holds. `effect:enqueue_merge` and `effect:dequeue_merge` wait on the queue App, `combsmith-sf-queue`, with `contents` and `pull_requests` write alone, its key in an environment of its own ("A narrow queue App, combsmith-sf-queue, enqueues and dequeues with contents and pull-request write alone (P-2)", issue 381) | The Maintainer's choice, 2026-10-28 |
| The fake | `an_app_enters_the_queue` and `an_app_leaves_the_queue` are grounded on `trials/P-2.least.json`, with the permission they take | A rule a fixture shows is grounded on it |
| P-52's narrowed mint | `trials/P-52.narrowed.json`: the Controller's token minted with exactly `metadata` and `actions_variables` at read is answered with those, and reads both of the Pause's routes | The pass asks for that name; a refused name would stop every pass |
| A trimmed answer | Bulk a trial does not ask about is left out of an answer, and the call says what is kept: a mint's expiry, permissions and selection, as `tools/trial_as_app.sh` keeps them; an installation's identity and grants; a pull request's number, node, state, head and author; a comment's id, author and times, never its text | Each fixture of the window stays under the size a pull request carries |

## Why

A write a trial makes is what it asks; a fixture that could not hold one recorded only what came after. The exception is
as narrow as the writes the window made, and a node outside the canary cannot reach it, by the read that names it or
by the repository its id names.

## Boundaries

| Boundary | Check |
|---|---|
| A write is one of `WRITES`, on a node a read of the canary alone answered, whose id is the canary's | `tests/test_tools.py::test_a_write_is_recorded_only_on_a_node_a_read_of_the_org_answered`, `tests/test_tools.py::test_a_cost_measurements_exchanges_name_each_repo_they_span` |
| The queue's writes wait on the queue App; the queue's read is the Controller's at metadata read | `tools/check_apps.py` |
| The two queue rules of the fake are grounded on P-2, and its refusals are placed | `tools/check_trials.py`, `tests/test_adapters.py::test_a_recorded_refusal_is_no_answer` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
