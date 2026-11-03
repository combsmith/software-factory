# 0126. A created check replaces only an earlier created one of its name, and three of P-42's check rules are grounded

Status: accepted. The Factory Builder's ask of 2026-11-03 on "The status rollup keeps one run of a name in each check suite, so three rules of the fake go beyond what GitHub gives (P-42)" (issue 496), from `trials/P-42.rollup.json` and `trials/P-35.json`. It changes decision 0091's row "The fake's check rules": three of the rules it left unverified are grounded.

## Decision

| What | Decided | Because |
|---|---|---|
| What the status rollup leaves out | `a_check_is_read_by_name_from_every_app` now says the rollup leaves out only a run that its job's re-run, or a later check created under its name in its suite, replaced. It is grounded on `trials/P-42.rollup.json` | The rollup held the same runs as `filter=latest`, by id, on two heads with four and five Apps, and left out exactly those two kinds of earlier run |
| What replaces a run | `a_rerun_replaces_only_its_own_run` now says a re-run replaces only its job's earlier run, a created check only one created earlier under its name, and that a job's run and a created check of one name both stay. It is grounded on the same fixture | `trials/P-35.json` kept a job's run and a created check of one name in one suite, whichever came first. The issue's fear, a created check standing in place of a Lens's own run, has not been seen |
| The fake | A check a job creates under a Lens's name now replaces a check created earlier under that name, and stands beside the Lens's own run and beside another workflow's or App's, as before. One job's re-run also gave its run's other jobs new check runs with their old conclusions; that changes no verdict, so the fake does not model it | That is what both fixtures show |
| A replaced Lens | Were a Lens's run replaced by a created check, the Kernel would read the created check with no file (decision 0104), so the Lens is unreadable: a queued item leaves the queue, and any other defers. No Kernel change | A forged success that hid a real failure would admit nothing |
| Timeouts | `a_check_can_time_out_or_give_no_verdict` now says a check times out as `cancelled`, or gives no verdict as `neutral` or `skipped`, and is grounded on `trials/P-42.json`. `timed_out` and `stale` move to `a_check_concludes_timed_out_or_stale`, which no trial can ask, and the fake still gives both | GitHub concluded a job stopped at its timeout `cancelled` (decision 0091); the checks API still lists both words |
| How each is read | Each of the three is named in `NOT_READ` as `shape`: P-42.rollup's read lacks a check run's `completedAt` and `detailsUrl`, and P-42's are REST lists | The port reads the rollup with both, so a trial that records the port's own read holds them |

## Why

P-42.rollup showed the read the checks port makes leaving earlier runs out, and the three rules said more than GitHub gives. Read beside P-35, what it leaves out is narrow: a re-run's earlier run, and a created check's earlier created one. A job's own run is never left out for a created check.

## Boundaries

| Boundary | Check |
|---|---|
| Were a Lens's run replaced in its own suite by a created check under its name, it would admit nothing: a queued item leaves the queue, and any other defers | `tests/test_decide.py::test_a_lens_run_replaced_in_its_suite_by_a_created_one_admits_nothing` |
| A created check stands beside the Lens's own run and another workflow's or App's, and replaces only one created before it | `tests/test_simulator.py::test_a_created_check_stands_beside_the_lens_run_and_replaces_only_one_created_before` |
| A rule a fixture grounds is read by the port, or named read in another shape | `tests/test_adapters.py::test_the_port_reads_each_grounded_rule_as_the_fake_assumes_it` |
| Each of the fake's new paths has a mutant that a test kills | `tools/mutants.py` |
