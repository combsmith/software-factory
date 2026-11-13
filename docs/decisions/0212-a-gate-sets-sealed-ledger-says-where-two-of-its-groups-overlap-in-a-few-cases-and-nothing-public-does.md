# 0212. A gate set's sealed ledger says where two of its groups overlap in a few cases, and nothing public does

Status: accepted. The Factory Builder's rulings of 2026-11-12 and 2026-11-13 on "Differences between a gate set's manifests across commits can isolate a group under ORIGIN_LEAST" (issue 695): an advisory and no refusal, and, on the 13th, told in the sealed ledger alone. It takes up one residual of `docs/decisions/0180-a-gate-set-holds-a-floor-per-criterion-read-from-each-cases-expected-criterion.md`: "the least holds for each group, not for where two overlap". All of 0180 stands.

## Decision

| What | Decided | Because |
|---|---|---|
| A cell | A kind; for the cases that expect a Finding, the criterion the set floors or none of them; and natural or not | The groups a report counts are the kinds, each floored criterion's findings, and the natural cases and the others. Every sum or difference of their counts is of whole cells |
| What is told | `cells`, in `eval-ledger/1`: each cell that holds a case, with how many it holds, and `ok` where every one holds `ORIGIN_LEAST` at least. Null where a case was not read or its answer is no kind | Where two groups overlap in a cell of a few cases, their counts' difference tells those few. The Maintainer needs which cell, and how short, to decide what to do with the set |
| Where | In the ledger alone, which is sealed to the Maintainer's certificate and never uploaded in the clear. He sees it when he opens the ledger, which is when he reads the set | The ledger already holds each case and its Result |
| Nothing public | The report gains no field, and neither the fetch's line nor the job's says anything of the cells | A public word is not harmless, even one word. Suppose a report counts as many findings on a floored criterion as its manifest marks cases natural. A word that every cell is whole would then say that the marked cases, which the manifest names by id, are that criterion's findings: the set's composition, which is held out. In general such a word says that every small row of the set is wholly natural or wholly not |
| It stops nothing | The fetch goes on, and no verdict reads the cells | A refusal could stop a set no builder can see, which is why 0180 left it. Turning it into a refusal is the Maintainer's, once he has read the set, and a record of its own then |
| Whose | A gate set's alone. A development set has no ledger, and counts no group | Its report lists each case |
| A required field | Every `eval-ledger/1` carries `cells`, or null | A ledger is written by the run that seals it, and nothing reads an earlier one |
| Residual: told, not closed | While a cell is a few cases, two groups' counts differ by those cases' verdicts, to whoever knows which cases are in both | Written down, as 0180 did. Closing it is the refusal above |
| Residual: no word at the dispatch | Nothing tells the Maintainer at the dispatch that a ledger is worth opening for this | The price of nothing public. He opens a gate set's ledger to read the set |

## Why

Decision 0180 holds each group a report counts to none or `ORIGIN_LEAST` cases, and wrote down that two groups may still overlap in fewer. A rule at the fetch that refused such a set could stop one no builder may read, so this tells and does not refuse. And what it tells is of the set's composition, so it is told where the composition already is, under seal, and to the one person who can act on it.

## Boundaries

| Boundary | Check |
|---|---|
| A cell is a kind, the floored criterion or none, and natural or not, with how many cases it holds. The cells are whole where each holds the least, at ten and not at nine. A criterion the set does not floor makes no cell of its own, nor does a clean case's criterion; each floored criterion does. A development set, and a set not read whole, have none | `tests/test_evals.py::test_a_gate_sets_sealed_ledger_says_where_two_of_its_groups_overlap_in_a_few_cases_and_nothing_public_does`, `harness/eval/__init__.py`, `tools/mutants.py`, mutant: "a cell of a few cases is whole", mutant: "a cell of the least is a few", mutant: "a cell holds the natural cases with the others", mutant: "a cell holds every criterion's findings together", mutant: "a cell holds both kinds together", mutant: "a criterion the set does not floor is a cell of its own", mutant: "a clean case's criterion makes a cell", mutant: "a development set is told of its cells", mutant: "a cell says not how many cases it holds" |
| The run writes the cells into the ledger it seals, and every ledger says them or null. The report holds nothing of them, the fetch's line and the job's are as they were, and neither a report's verdict nor the pool's is changed | `tests/test_evals.py::test_a_gate_sets_sealed_ledger_says_where_two_of_its_groups_overlap_in_a_few_cases_and_nothing_public_does`, `harness/eval/__init__.py`, `schemas/eval-ledger.schema.json`, `tools/mutants.py`, mutant: "the run tells the ledger nothing of the cells", mutant: "the ledger drops what it is told of the cells", mutant: "a ledger need not say its cells" |
