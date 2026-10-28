# 0079. The machine user's approval counts only for a pull request open when it was given, and never from before a reopening

Status: accepted. The Factory Builder's rulings of 2026-10-28 on
"The approving act refuses a pull request that is not open, since GitHub approves a closed one (P-7.refused)"
(issue 378), from P-7.refused's cases (1) and (4) in the second machine-user window. It extends decision 0055, on the
approving act, and leaves it as it is.

## Decision

| What | Decided | Because |
|---|---|---|
| Before the approval | The act reads the pull request open at the commit it approves; one closed or merged is refused, `superseded`, `not_open`, and one at another head `head_moved`, and nothing is sent. One that cannot be read is whose fault its status says | GitHub takes an approval of a closed pull request (P-7.refused's case (1)): the Kernel's read before the act does not stop one closed since |
| After the approval | Read back, the pull request is read again: one closed or merged under the act claims nothing, `failed`, `superseded`, `closed_under_act`, and no Effect lands, so reconciliation names the approval standing with none while the pull request is served in its window (decision 0061). One that cannot be read claims nothing; one at another head keeps its approval of the commit it read | A close between the read and the approval cannot be refused by GitHub, only seen |
| A reopening | The machine user's approval stands only if it was submitted after the pull request was last reopened, read from the timeline's `reopened` event as a new fact, `last_reopened_at`; on a timeline not read whole, none stands | GitHub reads an approval given while the pull request was closed approved again once it is reopened with no push (`trials/P-7.reopened.json`). Derived from the facts at every call, with no write, so such an approval never converges, even before anyone dismisses it |
| Recovery | The act recovers the approver's approval only while the pull request is open, on a timeline read whole, and never one submitted before its last reopening: a re-run after a close claims nothing, and after a reopening the act sends a fresh approval the Kernel still wants | Recovering either would claim, or stand on, an approval the Kernel does not count |
| A dismissal | Not made: the act does not dismiss its own approval | The Kernel's rule holds without it, and a dismissal on a closed pull request is unasked |

## Why

P-7.refused's case (1) found GitHub approves a closed pull request; its case (4) that the approval reads approved
again on a reopening with no push. The act's read before it and its read back after it close the window the act can
see; the Kernel's rule closes the one it cannot, whoever reopens the pull request and whenever.

## Boundaries

| Boundary | Check |
|---|---|
| A pull request not open at the commit is never approved, and nothing is sent | `tests/test_approve.py::test_a_pull_request_not_open_at_the_commit_is_never_approved` |
| A pull request closed under the act claims no approval | `tests/test_approve.py::test_a_pull_request_closed_under_the_act_claims_no_approval` |
| An approval from before a reopening never stands, and none stands on a timeline not read whole | `tests/test_decide.py::test_an_approval_from_before_a_reopening_never_stands` |
| A reopening is read from the timeline, the latest of them | `tests/test_adapters.py::test_a_reopening_is_read_from_the_timeline` |
| The snapshot holds when the pull request was last reopened | `tests/test_adapters.py::test_a_snapshot_holds_when_the_pull_request_was_last_reopened` |
| An approval from before a reopening is not recovered, and a fresh one is sent | `tests/test_approve.py::test_an_approval_from_before_a_reopening_is_not_recovered` |
| No approval is recovered on a timeline read short | `tests/test_approve.py::test_no_approval_is_recovered_on_a_timeline_read_short` |
| A re-run claims no approval of a pull request now closed | `tests/test_approve.py::test_a_re_run_claims_no_approval_of_a_pull_request_now_closed` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
