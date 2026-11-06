# 0143. An eval case's fault may be rightly placed at more than one place, and each is named blind

Status: accepted. The Maintainer's choice of 2026-11-05, after a private audit of the held-out set's misses: some faults have more than one place a careful reviewer could rightly put them, and a case's answer names only one. It adds to `eval-case/1` and to `tools/eval_result.py`. The gate, its bar and each kind's bar (decision 0120) do not change.

## Decision

| What | Decided | Because |
|---|---|---|
| The case | An expected Finding may carry `also_at`, a list of one location or more, each shaped as `location` is, with its own path and lines. Absent, the Finding has one place, its `location`, as before. An empty list, or an entry that is not a location, fails the schema | A fault that spans several changed lines, or several files of one change, is rightly placed on any of them: the line that brings it in, the line that uses it, the file that causes it. A key that names one of them fails a reviewer who chose another for no fault of its reading |
| The score | A raised Finding is at the expected place when it overlaps `location` or any entry of `also_at`, by the rule `location` is read by. That holds for the Finding that cites the criterion, and, for one that does not, for whether it is at the place, `finding_uncited` or `finding_cites_another`, or in a file of one of them but elsewhere, `finding_elsewhere` | One fault, several places: every other place the scorer looks must agree with the first, or a Finding passes on one reading and is said elsewhere on another |
| What is unchanged | Category, severity and criterion are the case's one answer, whichever place the Finding is at. A Finding must still be the expected one in every respect | A place is where the fault can be read; what the fault is does not move with it |
| A place unreadable | Every place a case gives must be readable: an entry of `also_at` whose end has no start, or comes before its start, makes the case `location_unreadable`, as its `location` does. One given without lines is the whole file | A place that cannot be read would be read as nowhere, and a case would pass or fail on what its key cannot say |
| How places are added | By an audit of the private set that does not see the model's answers, to every case alike, each justified on its own diff in the private home. Never to the cases a run failed alone | A place added where the model put its Finding would mark the model's answer right because it was the model's |

## The cost

A looser key can only raise the score: a place added never fails a Finding that passed. So `also_at` moves the bar closer for every case it is given to, and the gate measures less than it did unless each place is one a careful reviewer would rightly choose. That is why places are added blind, to every case, and justified case by case where the cases are; it is not checked here, since no session here reads a case.

## Why

The private audit found misses where the review raised the right fault, rightly placed, at a line or file the key did not name. A key that names every right place measures the review's judgment rather than its luck in choosing the one place written down. The scorer, the schema and the rule for adding places are here; the places themselves, and any count of them, stay in the private home.

## Boundaries

| Boundary | Check |
|---|---|
| A Finding at any place a case gives is at the place, citing or not, with category and severity unchanged; absent `also_at`, `location` alone; every place readable, or the case is unreadable; the schema refuses an empty list or an entry that is no location | `tests/test_evals.py::test_a_finding_at_any_place_the_case_gives_is_at_the_place` |
| A case with `also_at` is an example, and one with an empty list, or an entry with no path, a counter-example | `tools/check_examples.py`, `examples/eval-case.also-at.json`, `examples/invalid/eval-case.no-place-in-also-at.json`, `examples/invalid/eval-case.a-place-in-also-at-with-no-path.json` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
