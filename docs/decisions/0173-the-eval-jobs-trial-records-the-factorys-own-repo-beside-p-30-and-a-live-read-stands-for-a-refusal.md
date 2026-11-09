# 0173. The eval job's trial records the Factory's own repo beside P-30, and a live read stands for a refusal

Status: accepted. The Factory Builder's rulings of 2026-11-09 on the fixtures of "Epic: slice 1, first approval. A Release on next reviews a pull request to this repo, and the machine user's approval stands" (issue 182), for "Workflows: eval.yml runs the review Intent's held-out cases and writes eval-report/1" (issue 309) and "Trial P-30: one identity cuts a Release and moves a channel tag under the tag ruleset" (issue 189). Pre-approved by the Maintainer on 2026-11-08. It amends decision 0113's row "Which trials may", whose "P-30 alone" now reads "P-30 and P-63 alone", and changes nothing else of it.

## Decision

| What | Decided | Because |
|---|---|---|
| The eval job's trial | P-63, a new row of section 6: the job, run from `main`, reads the private held-out home with `factory-eval`'s secret and uploads its `eval-report/1` by hashes alone, and that environment is refused to every other branch. `trials/P-63.json` records run 42347416962, the gate's run for the Release v0.1.0 | The eval job's story asks a platform trial to record the job, and no row of section 6 asked it |
| Where it records it ran | `combsmith/software-factory`: `TRIALS_OF_THE_FACTORY` in `tools/check_trials.py` names P-63 beside P-30, and still no other | The job and its environment are this repo's, and the canary has neither, as with P-30's tag ruleset under 0113 |
| What it keeps of the report | The report's commit, Release, set, totals and one-word bars, and each case by its id and sha256 alone. Each case's verdict and reasons are left out, and the archive's own sha256 is the artifact's digest GitHub lists | A reason such as `finding_not_raised` tells a case's kind, and no count of a kind is written in this repo (decision 0120). The id and the hash are already `evals/pr-review/cases.json`'s |
| What stands for a refusal | P-63: `factory-eval`'s one deployment branch policy, `main`, with no admin bypass, read live, stands for a dispatch from another branch refused. P-30: tag ruleset 25183656's bypass list, the admin role and the release App alone, read live, stands for each other identity's refusal. Each fixture states its residual in its pass condition: no dispatch from another branch, and no other identity's refusal, was exercised | A rule GitHub enforces, read as it stands, says whom it refuses. Exercising each refusal needs a dispatch the Maintainer alone makes, or a credential for each identity, which no session holds |
| P-30 | `trials/P-30.json` records release runs 42348605675, which cut the Release v0.1.0 and moved the channel tag v0-next to it, its Deployment naming the release App as creator, and 42348650504, the same cut refused, with both tag rulesets and the repo's admins read live. Decision 0114 is why the release App and not the poller's job token | The first two boxes of P-30's story |
| When each pass condition was written | After the runs, from the story's own condition as the ruling of 2026-11-09 stands it in. This sets aside, for these two fixtures alone, the trial skill's step 1, that the condition comes before anything runs: the runs were the Maintainer's dispatches for the Release, made before any trial was asked of them, and each condition names its stand-in and residual rather than fitting the answer | A fixture of a run already made can only be written after it; saying so is better than a condition that reads as written first |

## Why

Both stories needed a fixture to close, and both runs had already happened. A fixture made from those runs, with the rule that refuses everyone else read beside it, says what happened and what it stands on, and names what it does not show.

## Boundaries

| Boundary | Check |
|---|---|
| P-63 recorded on this repo holds, and recorded on the canary is refused | `tests/test_tools.py::test_the_eval_jobs_trial_records_the_factorys_own_repo`, `tools/check_trials.py`, mutant: "the eval job's trial is no trial of the Factory" |
| No trial but P-30 and P-63 records this repo | `examples/invalid/trial.another-trial-in-the-factorys-repo.json`, `tests/test_tools.py::test_a_cost_measurements_exchanges_name_each_repo_they_span`, `tools/check_trials.py`, mutant: "any trial may record the Factory's own repo" |
