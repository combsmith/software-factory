# 0212. A gate set's report says in one word whether two of its groups overlap in a few cases, and stops nothing

Status: accepted. The Factory Builder's rulings of 2026-11-12 and 2026-11-13 on "Differences between a gate set's manifests across commits can isolate a group under ORIGIN_LEAST" (issue 695): an advisory at the fetch and no refusal, told in one word. It takes up one residual of `docs/decisions/0180-a-gate-set-holds-a-floor-per-criterion-read-from-each-cases-expected-criterion.md`: "the least holds for each group, not for where two overlap". All of 0180 stands.

## Decision

| What | Decided | Because |
|---|---|---|
| A cell | A kind; for the cases that expect a Finding, the criterion the set floors or none of them; and natural or not | The groups a report counts are the kinds, each floored criterion's findings, and the natural cases and the others. Every sum or difference of their counts is of whole cells |
| The word | `cells_ok`, in `eval-aggregate/1`: true where every cell holds none of the cases or `ORIGIN_LEAST` at least, false where one holds a few, null where the kinds are. One word of the whole set, and never which cell or how many | Naming the cell, or its count, would publish the set's composition, which is held out |
| Where it is told | The fetch's line and the job's one line both say that two groups overlap in fewer than the least. It is read from the fetched cases, as the kinds and the floors are | The Maintainer, who alone dispatches a gate set, sees it at the dispatch |
| It stops nothing | The fetch goes on, and the verdict of a report and of the pool never read the word | A refusal could stop a set no builder can see, which is why 0180 left it. Turning the word into a refusal is the Maintainer's, once he has read the set privately, and a record of its own then |
| Whose | A gate set's alone. A development set counts no group and is told nothing | Its report lists each case |
| A required field | Every `eval-aggregate/1` carries the word | As 0180 made its counts. Every report the gate pools is the job's own, at one commit |
| Residual: told, not closed | While a cell is a few cases, two groups' counts differ by those cases' verdicts, to whoever knows which cases are in both | Written down, as 0180 did. Closing it is the refusal above |
| Residual: the word is public | A report whose word is false says that its set has such a cell, though not which | The Factory Builder ruled it told; what it tells is one bit of the set, and no case |

## Why

Decision 0180 holds each group a report counts to none or `ORIGIN_LEAST` cases, and wrote down that two groups may still overlap in fewer. A rule at the fetch that refused such a set could stop one no builder may read. A word that says so, and stops nothing, tells the one person who can read the set that it is worth reading, at the moment he dispatches it.

## Boundaries

| Boundary | Check |
|---|---|
| A cell is a kind, the floored criterion or none, and natural or not. One of a few cases makes the word false, at nine and not at ten; a cell of none is whole. A criterion the set does not floor makes no cell of its own, nor does a clean case's criterion; each floored criterion does. A development set, and a set not read whole, are told nothing | `tests/test_evals.py::test_a_gate_sets_report_says_whether_two_of_its_groups_overlap_in_a_few_cases_and_stops_nothing`, `harness/eval/__init__.py`, `tools/mutants.py`, mutant: "a cell of a few cases is whole", mutant: "a cell of the least is a few", mutant: "a cell holds the natural cases with the others", mutant: "a cell holds every criterion's findings together", mutant: "a cell holds both kinds together", mutant: "a criterion the set does not floor is a cell of its own", mutant: "a clean case's criterion makes a cell", mutant: "a development set is told of its cells" |
| The report carries the word; the job's line and the fetch's say it in words that hold no count of a cell and name none; and neither a report's verdict, the pool's, nor the fetch is stopped by it | `tests/test_evals.py::test_a_gate_sets_report_says_whether_two_of_its_groups_overlap_in_a_few_cases_and_stops_nothing`, `harness/eval/__init__.py`, `tools/mutants.py`, mutant: "the report says every set's cells are whole", mutant: "a set that was not read is advised of an overlap", mutant: "the job's line says nothing of an overlap", mutant: "the fetch says nothing of an overlap", mutant: "an overlap stops the dispatch at its fetch" |
