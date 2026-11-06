# NNNN. A Finding that would hold a clean change fails its case, whatever criterion it cites

Status: accepted. The Maintainer's ruling, restated to this lane by the Builder on 2026-11-06: a gating Finding raised on a clean case fails that case, even where its criterion is covered as met. It changes `tools/eval_result.py` alone. The codes, `eval-report/1`, the gate, its bar and each kind's bar (decision 0120) do not change.

## Decision

| What | Decided | Because |
|---|---|---|
| The rule | On a case whose expected verdict is `met`, a raised Finding that would hold the pull request fails the case with `finding_raised_wrongly`, whatever criterion it cites, another or none, and whatever the coverage says of the case's own criterion | A clean case holds no fault a gate should stop. A review that would hold that change sends a right change back to its author, which is the cost a false positive has in the Factory, whichever criterion it was filed under |
| What would hold it | A Finding of severity `blocking` or `major`, or of category `security` at any severity, as `kernel/gate.py` reads a required Lens's Finding: the scorer reads the gate's own `GATING_SEVERITIES` and `SECURITY`, and keeps no copy | The case fails on what the live gate would do with the Finding, so the two cannot drift apart |
| What is unchanged | A Finding that cites the case's own criterion still fails it at any severity, as before. A Finding that would hold nothing, minor or info and not security, cited elsewhere or not at all, still leaves the case to its coverage. The code given is `finding_raised_wrongly`, once, whatever number of Findings gave it. A case that expects a Finding is scored as before: a Finding elsewhere that would hold the change is no fault of it | The ruling is about the false positive that gates. A minor note elsewhere sends nothing back, and a case that expects a Finding already holds a fault the gate should stop |
| What makes it fair | Every clean case must hold no fault a gate should stop, anywhere in its diff, and not only none on its own criterion. Whether each does is checked by an audit in the private home, blind to the model's answers; no session here reads a case | A clean case with another real gating fault would now fail a review that rightly raised it. So the key must say clean of the whole change, as the rule now reads it |
| The cost | A stricter key can only lower the score: a case that passed may now fail, and none that failed now passes. The `met` kind's share falls where the review raised gating Findings off the case's criterion, and the run's bar does not move to meet it | Named so that a fall after this change is read as the rule's and not the Role's. It is the measure the gate should have held: a right change the review would send back is not a pass |

## Why

A clean case asked only whether the review raised a Finding against the one criterion the case is about. A review could cover that criterion as met, raise a blocking Finding against another criterion of the same right change, and pass, though the Factory would have held that change and sent it back. The score then said the review was right where the Factory would have been wrong. Reading the gate's own rule for what holds a change makes a clean case measure what a false positive costs, and nothing a minor note does not cost. The audit of the private set that keeps each clean case free of any gating fault is what keeps the rule from failing a review that was right; it stays in the private home, with every case.

## Boundaries

| Boundary | Check |
|---|---|
| On a clean case, a Finding fails it exactly where the gate would hold it, at every severity of every category, cited to another criterion or to none; one among others that would not still fails it, with one code; one citing the case's own criterion fails it at any severity; a case that expects a Finding is not failed by one elsewhere that would hold the change | `tests/test_evals.py::test_a_gating_finding_fails_a_clean_case` |
| A clean case whose Findings would hold nothing passes by its coverage, as before | `tests/test_evals.py::test_a_right_change_is_scored_by_its_coverage` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
