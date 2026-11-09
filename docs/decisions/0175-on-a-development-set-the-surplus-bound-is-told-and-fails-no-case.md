# 0175. On a development set the surplus bound is told and fails no case

Status: accepted. The Maintainer's ruling of 2026-11-09, given through the Factory Builder. It amends decision 0160 (issue 610, "The scorer bounds surplus Findings at and away from the expected place") for development sets until issue 582, "Raise the eval bar back toward record 0120's as recall improves", measures the bar again under the bound. The release gate's eval runs 42633372619 and 42636188085, both on b8d809b3, each closed the gate with "finding under its bar", at 24 and 25 of 40 cases passed. v0.1.0's run passed 27. In both runs, two cases failed on `surplus_at_place` or `surplus_gating_elsewhere` alone. Without those codes, the runs would have passed 26 and 27, at or near v0.1.0's level. The bar was set before decision 0160's scoring existed.

## Decision

| What | Decided | Because |
|---|---|---|
| A development set | A case the scorer fails on the surplus bound's codes alone, `surplus_at_place`, `surplus_gating_elsewhere` or both, is a pass in the report, and keeps its codes. It counts toward its kind's bar and the blocking word, as any pass does. A case that fails on any other code fails as before, with the surplus codes beside that code | The bar was measured before the bound, so the bound would move the gate by a scoring change and not by a change of the Role. The codes and `surplus_gating` still say where a review hedged |
| A gate set | Unchanged from decision 0160. The scorer's verdict stands, for the gate set's own cases and for the preflight its dispatch asks first | The ruling keeps the bound gating on gate sets. Their bars are their own and are stated with the bound in force |
| The report and `verdict` | On a development set's `eval-report/1`, a case is passed by its verdict and no code but the surplus bound's. A report that passes a case beside another code, or that fails a case on the surplus codes alone, is `count_differs`. That is no report the job writes | The Release's gate reads the report with this function, so it must hold to what the job now writes |
| The scorer | `tools/eval_result.py` is unchanged and still fails such a case. The harness reads the set's kind and decides | The scorer knows no set. The rule lives where the set is known |
| The cost | Until then a development set does not hold a review to one Finding at the place, or one gating Finding away from it. A Role that hedges, or scatters gating Findings, can pass a case there, and only the codes and `surplus_gating` show it. Such a pass is never marked `at_alternate`, since the scorer marks only its own passes, so a pass at a place of `also_at` alone is not counted in the run's line until then | The ruling accepts this for the time before the bar is re-measured. The report still shows each surplus, case by case, for that measure |
| Where it ends | When the bar is measured again under the bound, as the issue named above asks, a record ends this one's rule, and the bound gates development sets again as decision 0160 has it | The ruling is for the time before the bar is re-measured |

## Why

Decision 0160 changed what a pass is after the development set's bar was set. Two cases that v0.1.0's prompt and rubric passed now fail on the bound alone, and the gate closes on them, not on anything the Role does worse. Keeping the codes in the report shows how often the bound bites, which that re-measure needs in order to set the new bar. A gate set's bar is set with the bound, so it keeps gating there.

## Boundaries

| Boundary | Check |
|---|---|
| On a development set, a case that fails on the surplus codes alone is a pass, keeps its codes and its count, counts toward its kind's bar and the blocking word, and the report's `verdict` passes. Beside a miss, it fails by both codes | `tests/test_evals.py::test_the_report_counts_each_cases_gating_findings_away_from_the_place`, `tests/test_evals.py::test_each_kind_is_held_to_its_own_bar_where_the_cases_are`, `tests/test_evals.py::test_a_missed_blocking_case_is_said_and_closes_nothing_by_itself`, `harness/eval/__init__.py`, mutant: "a development set fails a case on the surplus bound alone", mutant: "a surplus code beside a miss passes the case", mutant: "a pass on the surplus bound alone clears no bar", mutant: "a surplus pass counts toward no kind's bar", mutant: "a surplus pass leaves the blocking word false" |
| On a gate set, the same case fails, counted under its kind and never as a fault. Its preflight fails the development set's cases on it too, and stops the dispatch | `tests/test_evals.py::test_a_gate_set_fails_a_case_on_the_surplus_bound_alone`, `harness/eval/__init__.py`, mutant: "a gate set passes a case on the surplus bound alone" |
| `verdict` passes a development set's case that carries the surplus codes alone. It reads as `count_differs` one that fails on them alone, or that passes beside another code | `tests/test_evals.py::test_the_gate_holds_each_kinds_bar_and_a_fault_still_closes_it`, `harness/eval/__init__.py`, mutant: "a development set's report may not pass a case on the surplus bound", mutant: "a report may fail a case on the surplus bound alone" |
