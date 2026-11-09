# NNNN. A gate set holds a floor per criterion, read from each case's expected criterion

Status: accepted. The Factory Builder's story of 2026-11-09, issue 692, "A gate set holds a floor per criterion, read from each case's expected criterion", a precondition of the first gate run. It adds to decision 0169's pooled gate a floor for each criterion a gate set names, and to decision 0164's report of counts alone the counts of each criterion. The Maintainer accepted publishing those counts.

## Decision

| What | Decided | Because |
|---|---|---|
| The floor | A gate set's manifest may give `criterion_bars`, `{criterion: [n, d]}`: of the cases whose `expected.criterion` is that criterion, summed over every dispatch the gate pools, at least n of d pass. A criterion the manifest does not name has no floor, and a floor on a criterion no case expects holds nothing | A gate set's bars are one per kind. A reviewer blind to one criterion can still clear both, so long as that criterion's cases are few among the Findings |
| Who may give one | Only a gate set, as with its bars and its least of a kind. Each floor is a whole fraction of at most one, of more than no case, on a criterion the rubric of the set's Role names; any other manifest is `eval_set_unreadable`. A set that gives floors states them in its record, after its bars, word for word (`bars_said`) | A floor can only add to what a gate set must clear, so it needs no bound below. One on a criterion no case can cite would hold nothing, and the record says what the gate is held to, as for the bars |
| Where the criterion is read | The job reads each case's criterion from the case it fetched, as `kinds_of` reads its kind. The manifest names no criterion per case | A manifest that named them would tell each case's criterion beside its id |
| The report | `eval-aggregate/1` gains `criteria`: of each criterion the set's cases expect, its cases, how many passed and their Wilson interval, counts alone, null where the kinds are. `aggregate_verdict` holds them to the set's counts: they add up to the set's cases and the report's passes, each interval its own, each named by a criterion's id, read where the kinds were; otherwise `count_differs` | So that each floor can be held over the pool, and a report the job did not write is refused |
| The gate | `pooled_verdict` sums each criterion's counts over the pool, after each kind has cleared its bar, and holds each named criterion to its floor. A pool under one is `criterion_failed`, whatever the others | The floor is the pool's, as a kind's bar is |
| What is public | Every gate report now says how many of the set's cases expect each criterion, and how many of them passed. No case's id, verdict or code is in it, as before | The Maintainer accepted this. A criterion's count is the least the floor needs |

## Why

A bar per kind cannot see a criterion. A gate set graded across several criteria could pass while the reviewer missed one of them every time, if that criterion's cases were few. A floor for each criterion the set's owner cares about closes that, and reading each case's criterion from the case itself keeps the manifest as silent as it was.

## Boundaries

| Boundary | Check |
|---|---|
| A pool under one criterion's floor fails with the others clear; exactly on it clears; the floor is summed over the pool; a criterion with no floor, or a floor no case expects, never fails one; a kind under its bar is said first. Counts that do not add up, an interval not its own, a criterion under any other name, or criteria left out where the kinds are read are `count_differs`. A development set may give no floor, nor may a gate set give one over one, of no cases, or on a criterion its rubric does not name; the record states the floors | `tests/test_evals.py::test_a_gate_set_holds_a_floor_per_criterion_over_the_pool`, `harness/eval/__init__.py`, mutant: "the pool holds no criterion to its floor", mutant: "a floor is held to one run's counts, not the pool's", mutant: "a development set may give floors", mutant: "a floor may name a criterion its rubric does not", mutant: "a floor may ask more than every case", mutant: "a floor of no cases is read", mutant: "the record need not state the floors", mutant: "a criterion's cases need not add up to the set's", mutant: "a criterion's passes need not add up to the report's", mutant: "a criterion's interval need not be its own", mutant: "a report may count under any word", mutant: "a report may leave the criteria out where the kinds are read" |
| The job counts each criterion from the cases it fetched, and the manifest names none | `tests/test_evals.py::test_a_gate_sets_report_counts_each_criterion_its_cases_expect`, `harness/eval/__init__.py`, `schemas/eval-aggregate.schema.json`, mutant: "the job counts no criterion" |
