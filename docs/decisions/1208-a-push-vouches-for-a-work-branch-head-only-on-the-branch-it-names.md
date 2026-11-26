# 1208. A push vouches for a work branch head only on the branch it names

Status: accepted. 2026-11-25, the Solution Architect; issue 1059. Extends decision 1207 and ends 1207's limit on a push to a later branch.

## Decision

A landed `push_commits` in `applied/1` names the work branch it landed on, `branch`, beside its commit's sha in `key` (`schemas/applied.schema.json`). The issues port tells `branch_pushed` true only where an earlier opening Run recorded pushing the head to the very branch the next opening would push to: `adapters/branches.py`'s `work_head` names that branch, and `adapters/applied.py`'s `landed` matches branch and commit. A push to another slot vouches for none of this one. A landed push read that names no work branch makes its record not whole, and the opening defers.

This ends decision 1207's limit that a Run whose opening did not land vouches for its push on any later branch.

Limits: no record names a branch until `apply`'s push writes one, which is not built yet. A branch moved onto the Factory's own commit at the slot that commit was pushed to still reads as pushed.

## Why

A commit is made for one issue's slot. A branch planted at another slot and moved onto it would otherwise be opened from as that issue's work. Recording the branch costs one field now, while no record exists; later it would be a schema change. Matching the commit alone, with the limit stated, was rejected.

## Boundaries

| Boundary | Check |
|---|---|
| A push vouches only for the branch it names; one naming no work branch defers | `tests/test_adapters.py::test_a_work_branch_head_the_factory_never_pushed_is_not_its_own`, `adapters/applied.py`, mutant: "a push to another branch vouches for its head" |
| The port asks of the branch whose head it read | `tests/test_adapters.py::test_a_work_branch_head_the_factory_never_pushed_is_not_its_own`, `adapters/issues.py`, mutant: "the port asks of no branch whose head it read" |
| `apply`'s push records the branch it landed on | waiting on `harness/push.py`, the push `apply` makes before the `open_pull_request` Effect |
