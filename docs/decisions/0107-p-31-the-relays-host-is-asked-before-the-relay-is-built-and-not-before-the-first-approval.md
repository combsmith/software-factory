# 0107. P-31, the relay's host, is asked before the relay is built, and not before the first approval

Status: accepted. The Factory Builder's ruling of 2026-10-31, on "Epic: slice 1, first approval. A Release on next reviews a pull request to this repo, and the machine user's approval stands" (issue 182). It decides one row of `docs/decisions/0043-a-scheduled-tick-is-a-backstop-of-hours-the-relay-carries-w-2-and-a-pass-records-what-started-it.md` otherwise, "The trials", which had P-31 join batch 2; the rest of that row stands.

## Decision

| What | Decided | Because |
|---|---|---|
| P-31 | It stands in no batch of section 6.1. It belongs to the relay and runs before the relay is built, in slice 3 | W-2 rests on the relay alone, and nothing else waits on what P-31 answers |
| The first approval | It does not wait on P-31. Batch 2 stays as it is otherwise, P-20 with it | It does not need W-2, since a Run's end starts its passes, as decision 0043 says |

## Why

Batch 2 is what stands before the first approval, so decision 0043's row named a batch its own reason did not call for. The audit of the path to the first approval found it, against the epic, which has P-31 gate only the relay.

## Boundaries

| Boundary | Check |
|---|---|
| P-31 stands in no batch of section 6.1, and section 6.1 says why | `tests/test_tools.py::test_the_relays_host_stands_in_no_batch_before_the_first_approval` |
| P-31 is asked before the relay is built, in slice 3 | Waiting on `controller/relay.py` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
