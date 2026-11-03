# 0126. The fake keeps the latest run of a name in each check suite, and three of P-42's check rules are grounded

Status: accepted. The Factory Builder's ask of 2026-11-03 on "The status rollup keeps one run of a name in each check suite, so three rules of the fake go beyond what GitHub gives (P-42)" (issue 496), from `trials/P-42.rollup.json`. It changes decision 0091's row "The fake's check rules": three of the rules it left unverified are grounded.

## Decision

| What | Decided | Because |
|---|---|---|
| The status rollup | `a_check_is_read_by_name_from_every_app` now says what the rollup holds: the latest run of each name in each check suite, from every App, never merged or renamed. It is grounded on `trials/P-42.rollup.json` | The rollup held the same runs as `filter=latest`, by id, on two heads with four and five Apps, and dropped an earlier run of a name in a suite |
| What replaces a run | `a_rerun_replaces_only_its_own_run` now says that a later run of a name in a suite, a re-run or a check a job created, replaces the earlier one there and nowhere else. It is grounded on the same fixture. One job's re-run also gave its run's other jobs new check runs with their old conclusions, which changes no verdict, so the fake does not model it | A re-run replaced its own run, the other suite's run of the name stayed, and a job's later created check replaced its earlier one in its suite |
| The fake | A check a job creates under a Lens's name, after the Lens failed, now lands either in another suite, beside the failure as before, or in the Lens's own suite, where it replaces the failure and stands alone in the facts. Which of the two is drawn from a stream of its own, so every other draw of each world is as it was | That is the case the rollup makes possible, and the one the Kernel must read safely |
| A replaced Lens | The Kernel reads the created check with no file (decision 0104), so the Lens is unreadable: a queued item leaves the queue, and any other defers. No Kernel change | A forged success that hides a real failure admits nothing |
| Timeouts | `a_check_can_time_out_or_give_no_verdict` now says a check times out as `cancelled`, or gives no verdict as `neutral` or `skipped`, and is grounded on `trials/P-42.json`. `timed_out` and `stale` move to `a_check_concludes_timed_out_or_stale`, which no trial can ask, and the fake still gives both | GitHub concluded a job stopped at its timeout `cancelled` (decision 0091); the checks API still lists both words |
| How each is read | Each of the three is named in `NOT_READ` as `shape`: P-42.rollup's read lacks a check run's `completedAt` and `detailsUrl`, and P-42's are REST lists | The port reads the rollup with both, so a trial that records the port's own read holds them |

## Why

P-42.rollup showed that the read the checks port makes keeps one run of a name in each check suite. The fake had kept a created check beside the failure it hid in every case, so it never served the Kernel the case the rollup can: the created check alone, in the Lens's own suite.

## Boundaries

| Boundary | Check |
|---|---|
| A Lens's run replaced in its own suite by a created check under its name admits nothing: a queued item leaves the queue, and any other defers | `tests/test_decide.py::test_a_lens_run_replaced_in_its_suite_by_a_created_one_admits_nothing` |
| A created check in a Lens's own suite is all the facts hold of the Lens; one in another suite stands beside the failure; a push leaves both behind | `tests/test_simulator.py::test_a_created_check_in_a_lens_own_suite_replaces_its_failure_and_one_elsewhere_stands_beside` |
| A rule a fixture grounds is read by the port, or named read in another shape | `tests/test_adapters.py::test_the_port_reads_each_grounded_rule_as_the_fake_assumes_it` |
| Each of the fake's new paths has a mutant that a test kills | `tools/mutants.py` |
