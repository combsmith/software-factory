# 1207. An opening holds on a work branch head the Factory never pushed

Status: accepted. 2026-11-25, the Solution Architect; issue 1059. Extends decisions 0239, 0242 and 1203, and amends design section 3.6.

## Decision

Where the next opening's work branch stands, the issues port tells whether an earlier opening Run of the issue recorded pushing its head: a landed `push_commits` in that Run's `applied/1`, keyed by the commit's sha. The fact is `branch_pushed`. Where it is false, the Kernel holds the issue, `branch_not_pushed`, and calls a person (`kernel/issue.py`). A fact not told defers the opening, as a branch not read does. Decision 0239's check at `apply` stays the second line.

Design section 3.6 now keys `push_commits` by the pushed commit's sha, read back, not by the branch head's tree digest.

The port reads the records only where the ref read finds a branch: two requests for each opening Run of the issue. So the last issue read a pass begins can pass decision 0234's budget by up to 390 requests and two for each such Run: 410 at the Run ceiling of ten. The figure is derived, never counted.

Limits: a record that expires before its branch does holds the issue until a person acts. So does a push GitHub accepted whose record never reached `applied/1`. The Run ceiling counts Runs since a person acted, so an issue's opening Runs, and the figure, can pass ten and 410.

## Why

The security read of pull request 1199 found that a branch planted at the next work branch's name would be opened from as the Factory's own; decision 1203 keeps every opener unnamed until a test tells the two apart. A tree digest names no commit, while decisions 0238 and 0239 compare the pushed commit's sha. A deferral was rejected: a planted branch does not mend itself, so a person is called.

## Boundaries

| Boundary | Check |
|---|---|
| A head no opening Run recorded pushing holds the issue for a person; a commit head not told so defers | `tests/test_issue.py::test_a_work_branch_head_no_opening_run_pushed_holds_the_issue_for_a_person`, `kernel/issue.py`, mutant: "a head the Factory never pushed is opened from" |
