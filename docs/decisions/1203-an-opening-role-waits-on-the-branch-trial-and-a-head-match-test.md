# 1203. An opening Role waits on the branch trial and a head match test

Status: accepted. 2026-11-25, the Solution Architect; issue 1059. Extends decisions 0234 and 0242.

## Decision

No Role is named to open pull requests while either is missing: trial P-80's fixture, its read of a work branch under the App's token (issue 1075), or the test `HEAD_MATCH` names. That test tells a work branch's head the Factory pushed from one it never did. `tools/check_authority.py` (`branch_read_problems`) holds the exact form. It reads both from the files and imports neither; one that cannot be read stays red, and the first part missing is named.

The writer's pull request may retire the counter-example `examples/invalid/config.an-opening-role-with-no-branch-read.json` only once this guard is in.

Limits: the guard sees that the trial and the test exist, not what they found or hold. A test of that name that matches nothing passes it. A pass's issue reads can now pass their budget by up to 390 requests, not decision 0234's 289: the last read begun adds the work branch's read, up to 101 more (decision 0242's limit row). The figure is derived, never counted, and the budget works as before.

## Why

Once issue 1059's part 3 reads the work branch, the guard passed this repo. Nothing then kept an opener unnamed until trial P-80 shows the read works under the App's token. Nor until a branch planted at the next name is told from the Factory's own (the security read of pull request 1199). No Role can open a pull request before a pulls-writing adapter exists, so this lands first, before the writer's.

## Boundaries

| Boundary | Check |
|---|---|
| A Role named to open pull requests waits on trial P-80's fixture, missing or not JSON | `tests/test_tools.py::test_a_role_named_to_open_pull_requests_waits_on_the_branch_read`, `tools/check_authority.py`, mutant: "an opening Role need not wait on trial P-80" |
| It then waits on the test `HEAD_MATCH` names, defined at any depth of its module, never in a comment | `tests/test_tools.py::test_a_role_named_to_open_pull_requests_waits_on_the_branch_read`, `tools/check_authority.py`, mutant: "an opening Role need not wait on the test that tells a head the Factory pushed" |
