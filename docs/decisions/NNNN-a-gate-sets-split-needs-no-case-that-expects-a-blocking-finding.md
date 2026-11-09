# NNNN. A gate set's split needs no case that expects a blocking Finding

Status: accepted. The Factory Builder's story of 2026-11-09, issue 691, "A gate set's split needs no case that expects a blocking Finding", raised by the Evals v2 work as a precondition of the first gate run. It amends decision 0150's blocking word for gate sets alone: a development set still holds one such case, `BLOCKING_LEAST`, or `split_ok` is false.

## Decision

| What | Decided | Because |
|---|---|---|
| A gate set's split | For a gate set, `split_ok` asks only that the set holds `kind_least_of` cases of each kind. It asks no case that expects a blocking Finding | A gate set brings its own bars and its own least of a kind (decision 0169). One built to grade only what no deterministic check holds may hold no blocking case, since the defects a blocking Finding marks are mostly ones a check holds. Under the old rule such a set was `eval_split_short` on every run, so its gate could never pass |
| The blocking word | Still computed and reported for a gate set, pooled as decision 0169 has it. It closes nothing by itself, as decision 0150 has it. Of a gate set with no blocking case it is true, as of any set with none | The word stays in sight where there are blocking cases. Where there are none it has nothing to hold, and the split no longer asks it to |
| A development set | Unchanged. It holds `BLOCKING_LEAST` cases that expect a blocking Finding, or `split_ok` is false | Decision 0150's reason stands for it: a true word for blocking cases must not mean that none exist |

## Why

The rule that a set holds a blocking case was made for the one set there was, the development set, so that its blocking word could not be true of nothing. A gate set is judged by its own bars and least of a kind, and its blocking word already closes nothing. Holding it to a blocking case would only make a gate set of the cases a model alone can judge impossible to pass.

## Boundaries

| Boundary | Check |
|---|---|
| A gate set with no blocking case and its kinds at their least is split, and `aggregate_verdict` and `pooled_verdict` pass a good report of it. Its own least of a kind still holds it. The same cases as a development set are short of a blocking case, and a development set with one is split | `tests/test_evals.py::test_a_gate_set_needs_no_case_that_expects_a_blocking_finding`, `tests/test_evals.py::test_a_missed_blocking_case_is_said_and_closes_nothing_by_itself`, `harness/eval/__init__.py`, mutant: "a gate set is held to a blocking case again", mutant: "a set may hold no blocking case" |
