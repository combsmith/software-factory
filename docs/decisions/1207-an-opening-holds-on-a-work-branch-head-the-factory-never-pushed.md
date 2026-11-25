# 1207. An opening holds on a work branch head the Factory never pushed

Status: accepted. 2026-11-25, the Solution Architect; issue 1059. Extends decisions 0239, 0242 and 1203, and amends design section 3.6.

## Decision

Where the next opening's work branch stands, the issues port tells whether an earlier opening Run of the issue recorded pushing its head, by its sha in that Run's `applied/1`: `branch_pushed`. False holds the issue, `branch_not_pushed`, and calls a person (`kernel/issue.py`); a fact not told defers the opening. Decision 0239's check at `apply` stays the second line.

Design section 3.6 now keys `push_commits` by the sha of the commit the Run itself pushed, not the branch head's tree digest. The head read back is compared with it, never recorded in its place.

The port reads the records only where a branch stands, two requests for each opening Run of the issue. The last issue read a pass begins can then pass decision 0234's budget by 390 requests and two for each such Run: 410 at the Run ceiling of ten. The figure is derived, never counted.

Limits: a record that expires before its branch does holds the issue until a person acts, as does a push whose record never reached `applied/1`. The Run ceiling counts Runs since a person acted, so the figure can pass 410. A push to an earlier work branch counts too: a branch moved onto it reopens work a person closed, which `max_unmerged_closes` bounds. A forged dispatch named as an opening Run defers the issue while GitHub lists it.

## Why

The security read of pull request 1199 found that a branch planted at the next work branch's name would be opened from as the Factory's own; decision 1203 keeps openers unnamed until a test tells the two apart. A tree digest names no commit, while decisions 0238 and 0239 compare the pushed commit's sha. A deferral was rejected: a planted branch does not mend itself.

## Boundaries

| Boundary | Check |
|---|---|
| A head no opening Run recorded pushing holds the issue for a person; a commit head not told so defers | `tests/test_issue.py::test_a_work_branch_head_no_opening_run_pushed_holds_the_issue_for_a_person`, `kernel/issue.py`, mutant: "a head the Factory never pushed is opened from" |
