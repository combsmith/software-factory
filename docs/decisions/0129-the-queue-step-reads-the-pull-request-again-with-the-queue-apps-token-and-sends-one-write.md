# 0129. The queue step reads the pull request again with the queue App's token, and sends one write

Status: accepted. The Factory Builder's rulings of 2026-11-03 on the queue step of "A narrow queue App, combsmith-sf-queue, enqueues and dequeues with contents and pull-request write alone (P-2)" (issue 381), part of "Epic: slice 1, first approval. A Release on next reviews a pull request to this repo, and the machine user's approval stands" (issue 182): its second part, the queue App's act, its port and its step, of three. It builds what decision 0128 left as not built, but the workflow files and reconciliation.

## Decision

| What | Decided | Because |
|---|---|---|
| The act | `harness/queue.py` takes the Decision from the pass record by its own Run id, an act the queue App makes, or does nothing (`no_decision`). It reads the pull request again with the queue App's own token and makes the one write: an enqueue or a dequeue only while the pull request is open at the head the pass read beside the Decision (`closed_under_act`, `head_moved`, `head_unknown`), a resolution only of a thread still open | A Run carries out what its Decision admitted and nothing else, on the item as it was decided on |
| Ruling A: no Kernel re-ask | The act does not ask the Kernel again, as the approving act does (I-38). The queue App's token reads the pull request and its threads and nothing else (trials/P-2.queue-app.json), so it cannot read the facts the Kernel would need | A narrow re-read with the App's own token keeps the key's reach at the three acts and their reads |
| The Pause | The job reads `FACTORY_PAUSED` from its `vars` context and sends nothing, and mints no token, unless it is exactly unset or `false` (`paused`) | A Pause set after the pass dispatched the act still stops it |
| The enqueue's head | `enqueuePullRequest` is sent with `expectedHeadOid`, the head the pass read; GitHub refuses it once the head moved (trials/P-57.json) | A push between the pass's read and the job's is never enqueued |
| What is claimed | Each write is read back: an enqueue and a dequeue are applied only on the merge queue entry GitHub answers with, a resolution only when GitHub answers it resolved by the queue App's login, and a thread already resolved is recovered as `already_applied` with nothing written. The step records `applied/1`, with Effect types `enqueue`, `dequeue` and `resolve_thread`, and `outcome/1`, and fails by its code | Nothing is claimed that was not seen, as every write port has it |
| Two tokens | The step finds the pass record with the job's own `GITHUB_TOKEN`, narrowed to reads of the item's repo, and mints the queue App's token from `QUEUE_APP_KEY` with the grants of its three acts alone, after the record, the Decision and the Pause are read; it is revoked when the act ends, and a revoke that fails is a fault | The key is used only for the write it is held for |
| Residuals | A Hold placed between the pass and the job is not seen; an enqueue can be dequeued, and a resolution closes only on the Lens's accepted ruling or decision 0125's supersession. The `vars` context gives the most specific `FACTORY_PAUSED`, so a repo's own `false` masks an org's Pause from this read, though not from the pass's. P-57 recorded `expectedHeadOid` through the Maintainer's login; a trial with the queue App's own token is owed | Named so that none is mistaken for held |
| What is not built | The queue workflow and its job's file, and naming `workflows.queue` and `accounts.queue`, are the third part, the latter waiting on P-39's users read; reconciliation's matching of the queue App's writes to the queue job's own record waits for them | Until both are named, no queue act is dispatched (decision 0128) |

## Why

Decision 0128 made each queue act a dispatched Run, so that its step holds the queue App's key and leaves the record the Kernel counts from. This builds that step on the same pattern as the approving act, narrowed to what the queue App's token can read.

## Boundaries

| Boundary | Check |
|---|---|
| The queue App's token sends its three acts and their reads, at the item, and nothing else | `tests/test_queue.py::test_the_queue_apps_token_sends_its_three_acts_and_reads_and_nothing_else` |
| Each document sent is the one a trial sent | `tests/test_queue.py::test_each_document_is_the_one_a_trial_sent` |
| An enqueue is made at the head decided on, bound by `expectedHeadOid`, and read back; a closed or moved pull request is sent nothing | `tests/test_queue.py::test_an_enqueue_is_made_at_the_head_decided_on_and_read_back` |
| A dequeue is made at the head decided on and claims nothing it did not see taken | `tests/test_queue.py::test_a_dequeue_is_made_at_the_head_decided_on_and_claims_nothing_it_did_not_see_taken` |
| A thread is resolved unless it is already, and claimed only as the queue App's | `tests/test_queue.py::test_a_thread_is_resolved_unless_it_is_already_and_read_back_as_the_queue_apps` |
| No Decision, a Pause or no head sends nothing | `tests/test_queue.py::test_no_decision_a_pause_or_no_head_sends_nothing` |
| The step reads with the job's token and writes with the queue App's | `tests/test_queue.py::test_the_step_reads_with_the_jobs_token_and_writes_with_the_queue_apps` |
| A record, a Decision or a key that cannot serve writes nothing | `tests/test_queue.py::test_a_record_a_decision_or_a_key_that_cannot_serve_writes_nothing` |
| The step writes its records and fails by its code | `tests/test_queue.py::test_the_step_writes_its_records_and_fails_by_its_code` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
