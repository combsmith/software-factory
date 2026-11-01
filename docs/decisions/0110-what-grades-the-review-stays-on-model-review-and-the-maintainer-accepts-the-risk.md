# 0110. What grades the review stays on model review, and the Maintainer accepts the risk

Status: accepted. The Maintainer's ruling of 2026-11-01, as the Factory Builder relayed it, on "Evals: the scorer and the set are no input of the review, so a change to what grades it needs no person" (issue 471).

## Decision

| What | Decided | Because |
|---|---|---|
| The paths | No person's approval is asked of a change to the scorer, `tools/eval_result.py`; the set's manifest, `evals/pr-review/cases.json`; the eval's schemas; the eval job's workflow, `.github/workflows/eval.yml`; the held-out fetch, `adapters/heldout.py`; or what reads the Release's gate, `release/cut.py`, `release/rings.json`, `adapters/candidate.py`, `adapters/artifacts.py` and `.github/workflows/release.yml`. They stay on model review | He cannot approve his own pull requests, and only one other account has write, so a person's approval of each would stop this work |
| The accepted risk | A model-approved change could weaken what grades the model, or skip the Release's gate. Nothing stops it but that review, which is the reviewer the eval measures. The Maintainer accepts this | His ruling |
| What it leaves as it is | `harness/eval/` stays on the review's own inputs through `harness/`, by decision 0052, which this does not change | The ruling named no change to that row, and so a change to the job's modules still waits for a person once the Kernel decides |

## Why

Decision 0052 keeps a model Lens from being the only judge of what it is given and how its answer is taken. What grades its answer could be held the same way, and is not: the cost falls on every such change, and the risk is his to carry.

## Boundaries

| Boundary | Check |
|---|---|
| A change to each of these paths waits for no person, and one under `harness/eval/` does | `tests/test_decide.py::test_what_grades_the_review_stays_on_model_review` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
