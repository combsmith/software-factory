# 0110. What grades the review stays on model review, and the Maintainer accepts the risk

Status: accepted. The Maintainer's ruling of 2026-11-01, as the Factory Builder relayed it, on "Evals: the scorer and the set are no input of the review, so a change to what grades it needs no person" (issue 471).

## Decision

| What | Decided | Because |
|---|---|---|
| The paths | No person's approval is asked of a change to the scorer, `tools/eval_result.py`; the set's manifest, `evals/pr-review/cases.json`; `schemas/eval-case.schema.json`, `schemas/eval-report.schema.json` and `schemas/eval-set.schema.json`; the eval job's workflow, `.github/workflows/eval.yml`; the held-out fetch, `adapters/heldout.py`; or what takes the Release's gate, `release/cut.py`, `release/move.py`, `adapters/candidate.py`, `adapters/artifacts.py` and `.github/workflows/release.yml`. They stay on model review. The list is of what the ruling means, and closes nothing: what else they import is not on the review's inputs either | He cannot approve his own pull requests, and only one other person has write, so a person's approval of each would stop this work |
| Model review, of every class | `evals/` joins verify's inputs in `config/hooks.json`, so a pull request of a class the model need not read is reviewed when it changes the manifest, as for the rest. It is on no list of a person's | Nothing else put the manifest on model review for that class, and the ruling says it stays there |
| The accepted risk | A model-approved change could weaken what grades the model, or skip the Release's gate. Nothing stops it but that review, which is the reviewer the eval measures. The Maintainer accepts this | His ruling |
| Beyond what he named | These paths reach more than the grade: `.github/workflows/eval.yml` and `adapters/heldout.py` hold the held-out token and read the cases, and `.github/workflows/release.yml` holds the release App's key. A change could send them elsewhere, as it could before this record. This names what these paths carry; his ruling did not name it | So that a reader takes the risk whole |
| Decision 0109's sentence | That changing the prompt, the scorer or the set after reading the codes is his call stands as what he expects. No check holds it, as decision 0109 says | His ruling adds no guard, and takes back no word of that record |
| What it leaves as it is | `harness/eval/` stays on the review's own inputs through `harness/`, by decision 0052, which this does not change | The ruling named no change to that row, and so a change to the job's modules still waits for a person once the Kernel decides |

## Why

Decision 0052 keeps a model Lens from being the only judge of what it is given and how its answer is taken. What grades its answer could be held the same way, and is not: the cost falls on every such change, and the risk is his to carry.

## Boundaries

| Boundary | Check |
|---|---|
| A change to each of these paths waits for no person, and one under `harness/eval/` does | `tests/test_decide.py::test_what_grades_the_review_stays_on_model_review` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
