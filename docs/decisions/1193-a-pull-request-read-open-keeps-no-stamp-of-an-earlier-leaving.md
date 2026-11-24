# 1193. A pull request read open keeps no stamp of an earlier leaving

Status: accepted. 2026-11-24, the Factory Builder; issue 1191. Extends decision 1045, whose Limits line it makes hold.

## Decision

A pass that reads a pull request open, decided or left out, drops that number from `reconciled.left`, as a served issue drops its stamp (issue 916). `controller/reconcile.py` (`carried`) holds the exact form. An issue of the same number is no reopening.

Limits: `left` holds numbers alone, so a pull request of that number in another repository clears the stamp too (issue 1190). The pass serves one home repository, so this cannot happen today.

A pull request left out of the last pass and closed before the next is still read as leaving by no pass, as decision 1045 says. An old stamp no longer keeps it read until that stamp ages.

## Why

A pull request that left and was read open again kept its old stamp. Left out of a later pass and closed before the next, it was read as leaving by no pass. Once the window passed the old stamp, its hand approvals and taken heads dropped. A hand approval then read again raised a false `write_unmatched`, against decision 1045's "its entries stay for good".

## Boundaries

| Boundary | Check |
|---|---|
| A pull request read open drops its earlier stamp, an issue of its number does not, and its hand approval outlives the old stamp | `tests/test_reconcile.py::test_hand_and_taken_are_carried_until_the_window_passes_their_leaving`, `tests/test_controller.py::test_a_hand_approval_merged_between_passes_stays_information`, `controller/reconcile.py`, mutant: "a reopened one keeps its stamp" |
