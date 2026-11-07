# NNNN. The review Intent's bar is each kind's own, set under the measured recall to guard against regression

Status: accepted. The Maintainer's ruling, restated to this lane by the Factory Builder on 2026-11-06: re-baseline the eval bar for v0.1.0, the first Release. For the review Intent, this record's bar stands in place of the bar decision 0120 set: its 90% of the set, its 80% of each kind, and its rule that every case that expects a blocking Finding must pass. Nothing else of 0120 changes: what closes the gate whatever the bar, the split, the report and its words stand as 0120 decided them.

## Decision

| What | Decided | Because |
|---|---|---|
| The bar | Each kind is held to its own bar: at least 90% of the clean cases, those that expect a criterion met, and at least 30% of the cases that expect a Finding. They are `BAR_OF_A_KIND` in `harness/eval/__init__.py`, one table that `kinds_pass` reads in the job, where the cases are. Each is a whole fraction compared by multiplying, so a share exactly on the bar clears it | The Maintainer's ruling. Whole numbers, so that no rounding decides a boundary |
| What it is | A guard against regression, not the measure of a sound reviewer. It is set under the measured recall, so that the noise between runs cannot close it alone | In two private runs of the set, at medium and at high effort, recall on the cases that expect a Finding was about 40–45%, and the runs differed by about 2–3 cases. A bar at the measure would close on noise |
| What goes | 0120's bar of the whole set and of each kind. And the rule that every case that expects a blocking Finding must pass, whatever the bar | In both runs the model missed a case that expects a blocking Finding. A rule that no run of today's reviewer clears closes the gate to every Release and guards nothing |
| The blocking word | `blocking_pass` stays in the report, computed as before, and the judge's line still says "a blocking case not passed". It closes nothing by itself. A set still holds one such case, `BLOCKING_LEAST`, or `split_ok` is false | The recall work must show that miss going away, so it stays in sight. What 0120 accepted of the word, that it can tell which ids expect a blocking Finding, is unchanged |
| The set's share | `verdict` holds the report's own share of passed cases only to the lowest of the kinds' bars. Every set whose kinds clear their bars clears that too, so it changes no verdict on a report the job wrote. A report that says each kind cleared, with fewer cases passed than that, is `case_failed` | The verdict takes each kind's word from the job. Without a bar of the set, nothing else would hold that word to the report's own cases |
| What a pass needs | A set of at least one case, every case the manifest names once by its id and hash, no fault of the Engine or the run, `split_ok` true, and each kind's bar cleared. Everything else `verdict` checked before, it checks still | 0120's checks, but for its bar |
| How it rises | The bar rises as the measured recall rises, each time in a record of its own that names the runs that measured it. Work on recall comes in stories of its own | A guard that is never raised stops measuring anything |
| What it does not hold | No floor by criterion or by severity. A reviewer that raises nothing clears the clean cases and fails the 30%. One that raises a Finding on everything fails the 90%. A reviewer that finds one fault in three clears it | Said so that a green gate is not read as more than it holds |
| Where it sits | In `harness/eval/__init__.py`, where 0120's numbers sat. `tools/hooks/protected.py` does not hold that file yet, as 0120 said; decision 0117's rule, that what grades the review needs a person, still waits on its story | Unchanged from 0120 |
| What is public | This record, the code and the tests give no count and no id of the held-out set. The measures above appear only as rounded ranges | The held-out rule: nothing of the set but its manifest is here |

## Why

0120's bar was set before any run read a case with its issue, so that it could not be fitted to the results. The runs since have measured the reviewer, and today's reviewer cannot clear it. A gate that stays shut gives no signal, and it blocks the first Release. Set under what was measured, the bar still closes on a reviewer that gets worse, which is the regression a Release must not ship, and does not close on noise. Recall is raised in stories of its own, and the bar follows it up.

## Boundaries

| Boundary | Check |
|---|---|
| Exactly 30% of the cases that expect a Finding clears, and exactly 90% of the clean cases; one case under does not; each kind by its own bar | `tests/test_evals.py::test_each_kind_is_held_to_its_own_bar_where_the_cases_are` |
| The set's share is held only to the lowest kind's bar; a kind's word closes the gate by itself; a fault of the Engine or the run closes it whatever passed | `tests/test_evals.py::test_the_gate_holds_each_kinds_bar_and_a_fault_still_closes_it` |
| A case that expects a blocking Finding and was not passed is said, and closes nothing by itself, in the job and at the Release's gate | `tests/test_evals.py::test_a_missed_blocking_case_is_said_and_closes_nothing_by_itself`, `tests/test_release_step.py::test_the_eval_gate_is_closed_by_anything_not_read_whole_or_not_passed` |
| The job writes each kind's word against its own bar, and the judge holds it | `tests/test_evals.py::test_the_job_writes_each_kinds_word_and_the_judge_holds_it` |
| Each threshold, and the blocking rule's removal, has a mutant that a test kills | `tools/mutants.py` |
