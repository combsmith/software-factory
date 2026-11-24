# 1193. A pull request read open keeps no stamp of an earlier leaving

Status: accepted. 2026-11-24, the Factory Builder and the Solution Architect; issues 1191 and 1190. Extends decision 1045, whose Limits line it makes hold, and whose number-only leaving it narrows to the home repository.

## Decision

A pass that reads a pull request open, decided or left out, drops that number from `reconciled.left`, as a served issue drops its stamp (issue 916). `controller/reconcile.py` (`carried`) holds the exact form. An issue of the same number is no reopening.

A leaving drops only the rows of the pass's home repository, as the configuration spells it, which `controller/pass_.py` hands `carried`. This supersedes decision 1045's drop by number alone. A read open of any pull request of that number clears the stamp, however its repository is spelled: that only keeps rows longer, and a renamed or differently cased home still clears its own.

Limits: another repository's rows, and home rows spelled otherwise than the configuration, are never dropped: they stay for good, which raises more alarms, never fewer. The day a pass serves more than one repository, `left` must hold the repository too, a schema change.

A pull request left out of the last pass and closed before the next is still read as leaving by no pass, as decision 1045 says. An old stamp no longer keeps it read until that stamp ages.

## Why

A pull request that left and was read open again kept its old stamp. Left out of a later pass and closed before the next, it was read as leaving by no pass. Once the window passed the old stamp, its hand approvals and taken heads dropped. A hand approval then read again raised a false `write_unmatched`, against decision 1045's "its entries stay for good". And `left` holds bare numbers, so one repository's leaving could drop another's rows of that number early, the unsafe direction (issue 1190).

## Boundaries

| Boundary | Check |
|---|---|
| A pull request read open drops its earlier stamp, an issue of its number does not, and its hand approval outlives the old stamp | `tests/test_reconcile.py::test_hand_and_taken_are_carried_until_the_window_passes_their_leaving`, `tests/test_controller.py::test_a_hand_approval_merged_between_passes_stays_information`, `controller/reconcile.py`, mutant: "a reopened one keeps its stamp" |
| Another repository's rows of that number survive the home repository's leaving | `tests/test_reconcile.py::test_hand_and_taken_are_carried_until_the_window_passes_their_leaving`, `tests/test_controller.py::test_a_hand_approval_merged_between_passes_stays_information`, `controller/reconcile.py`, mutant: "another repository's leaving drops its rows" |
| A read open clears its number's stamp however its repository is spelled; rows spelled otherwise than the home survive its leaving | `tests/test_reconcile.py::test_hand_and_taken_are_carried_until_the_window_passes_their_leaving`, `controller/reconcile.py`, mutant: "only the home as spelled clears a stamp" |
