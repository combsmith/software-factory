# 1207. An opening holds on a work branch head the Factory never pushed

Status: accepted. 2026-11-25, the Solution Architect; issue 1059. Extends decisions 0239, 0242 and 1203, and amends design section 3.6.

## Decision

Where the next opening's work branch stands, the issues port tells whether an earlier opening Run of the issue recorded pushing its head, by its sha in that Run's `applied/1`: `branch_pushed`. False holds the issue, `branch_not_pushed`, and calls a person (`kernel/issue.py`). An opening Run in flight, records not read whole, or a value told with no branch defer the opening. Decision 0239's check at `apply` stays the second line. The port's half lands with pull request 1208.

Design section 3.6 now keys `push_commits` by the sha of the commit the Run itself pushed, not the branch head's tree digest; the head read back is only compared with it.

The port reads the records only where a branch stands: one list and one download for each opening Run of the issue. The last issue read a pass begins can then pass decision 0234's budget by 390 requests and two a Run: 410 at the Run ceiling of ten, derived, never counted.

Limits: a record that expires before its branch does holds the issue, as does a push whose record never reached `applied/1`. Only a person moving or deleting the branch, or closing the issue, ends it. The Run ceiling counts Runs since a person acted, so the figure can pass 410. A Run whose opening did not land vouches for its push on any later branch too: a branch moved onto it reopens that work, which `max_unmerged_closes` bounds. A forged opening dispatch defers the issue.

## Why

The security read of pull request 1199 found that a branch planted at the next work branch's name would be opened from as the Factory's own. A tree digest names no commit, while decisions 0238 and 0239 compare the pushed commit's sha. A deferral was rejected: a planted branch does not mend itself.

## Boundaries

| Boundary | Check |
|---|---|
| A head no opening Run recorded pushing holds the issue for a person; a commit head not told so, or a value told with no branch, defers | `tests/test_issue.py::test_a_work_branch_head_no_opening_run_pushed_holds_the_issue_for_a_person`, `kernel/issue.py`, mutant: "a head the Factory never pushed is opened from" |
| `push_commits` is keyed by the sha of the commit the Run itself pushed, never by the head read back | waiting on `harness/push.py`, the push `apply` makes before the `open_pull_request` Effect |
| The port tells a head no opening Run of the issue recorded as not pushed, reading records only where a branch stands | `tests/test_adapters.py::test_a_work_branch_head_the_factory_never_pushed_is_not_its_own`, `adapters/issues.py`, mutant: "a head the Factory never pushed is told as pushed" |
