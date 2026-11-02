# 0051. The Controller's writes go through one credential each, held to what it may send, and every one is recorded

Status: accepted. Taken as a working ruling on 2026-10-21 for "Controller: one pass reads, decides, records, dispatches, writes the view and raises the reconciliation alert" (issue 193), its PR 2, the effects port's first commit, which the Maintainer may overturn in review. It adds to `docs/decisions/0003-one-controller-admits-every-run.md`, whose Runs it dispatches, and to `docs/decisions/0044-the-ports-are-the-one-place-that-reaches-the-network-through-one-transport-held-to-githubs-api.md`, whose transport it sends through.

## Decision

| What | Decided | Because |
|---|---|---|
| The plan | One pass's writes are planned by `controller/writes.py`, which reaches nothing, as `writes/1`, in the order they are sent: the acts no write serves yet, then the dispatches of Runs and approvals in the record's item order, then the successor last | A Run waits for a runner from as early as it can, and the next pass starts after this one's writes |
| Held to the record | Before anything is sent, the plan is held to the pass record it was planned from: the same pass and Release, ids in order, and every write but a last successor exactly the ones the record's Decisions call for, all of them, in their order, each dispatch under the run-name its Decision gives it, an approval's under the configuration's owner Role. A plan that is not the record's sends nothing. The successor alone is not in the record: it dispatches the poller, and carries nothing | A write the Kernel did not decide is never made (I-22) |
| A dispatch's credential | The pass job's own token, through a transport that may send only a dispatch of the three workflow files the configuration names, on the home repo and branch, a Run's or an approval's with its three inputs and the successor's with none. While the configuration names no account for that token, no Run or approval is dispatched | The records port counts a Run by that token's account (P-9); a Run it could not count, the ceilings would not see (I-34) |
| A dispatch's answer | Sent once, never retried, and recorded `sent`, never `applied`: GitHub's 204 names no run. A 401 or 403 ends every later write on that credential | A dispatch GitHub did not answer may still have started a run, and a second would start a second under the same Run id |
| The record of each write | `written/1`, beside `pass/1`, which is uploaded before the writes and never rewritten: each write's state, the key read back and a reason code. A plan refused whole, or a token the transport cannot take, still leaves it, every write refused. Nothing reads it to decide; a failed or refused write fails the step | The next pass derives every write again from GitHub (decision 0002); reconciliation will match the Controller's writes against it (I-33) |
| Not built yet | The status on the item, the dequeue, the tracking issue and the Pause read again before an act, each waiting on its trial (P-12, P-2) and, for the last three, on grants the Controller's App does not hold; an act no write serves is recorded `not_built` and raises nothing | A write with no trial behind it is not tested on a hand-made answer (L-51) |

## Why

The Controller's first part made the pass a pure function of what it read. Its writes reach GitHub, so they are a port's, through the one transport, and each needs a credential no other write shares, so that a stolen token can do only what its writes need and a review can read every write one token may make. The dispatch is the one write P-9 has tried; the rest wait on theirs.

## Boundaries

| Boundary | Check |
|---|---|
| The writes a pass plans go in their order | `tests/test_effects.py::test_the_writes_go_in_their_order` |
| A plan that is not its record's sends nothing | `tests/test_effects.py::test_a_write_list_that_is_not_the_records_is_refused_whole` |
| Each write goes through its one credential, which may send only its own requests, each by its path and the shape of its body | `tests/test_effects.py::test_each_write_goes_through_its_one_credential_and_its_allowlist` |
| No Run or approval is dispatched while the workflow token's account is unnamed | `tests/test_effects.py::test_nothing_is_dispatched_that_the_records_port_could_not_count` |
| A dispatch is sent once and never retried; a refused token ends every later write on it | `tests/test_effects.py::test_a_dispatch_is_sent_once_and_never_retried`, `tests/test_effects.py::test_a_refused_token_ends_every_later_write_on_it` |
| A dispatch is sent, never applied | `tests/test_effects.py::test_a_claim_is_only_what_was_read_back` |
| A failed or refused write is recorded and fails the step | `tests/test_effects.py::test_a_failed_write_is_recorded_and_fails_the_step` |
| A dispatch is answered as a trial recorded one: 204, with no body | `tests/test_effects.py::test_every_write_the_port_sends_has_the_shape_a_trial_recorded`; a dispatch of another file than the job's own, and one with no inputs, are not held yet: `tests/test_effects.py::test_a_dispatch_of_another_file_and_one_with_no_inputs_are_answered_as_a_trial_recorded` |
| The status on the item, the dequeue and the tracking issue are written as their trials recorded | The status: `tests/test_effects.py::test_the_status_reads_p12s_answers_as_they_stand`; the dequeue and the tracking issue, not held yet: `tests/test_effects.py::test_the_status_the_dequeue_and_the_tracking_issue_are_written_as_trials_recorded` |
| `writes/1` and `written/1` hold ids and codes alone | `examples/invalid/written.a-reason-in-words.json`, `examples/invalid/writes.a-write-the-port-does-not-send.json` |
