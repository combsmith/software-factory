# 0053. The eval job reads the held-out home with an App of its own, and reports hashes, verdicts and codes alone

Status: accepted. A working ruling of 2026-10-21 on "Workflows: eval.yml runs the review Intent's held-out cases and writes eval-report/1" (issue 309), with its amendments, which the Maintainer may overturn in review; the model credential's row is his rule of 2026-10-22. It decides one row of design §4.9's credentials table otherwise, and the form of the eval gate that the ruling on "Release: cut, promote and roll back the Factory's own Releases" (issue 197) reads.

## Decision

| What | Decided | Because |
|---|---|---|
| The job | The workflow eval.yml, `factory / eval`, on `workflow_dispatch` alone with one input, the Release it judges, run from the default branch at the commit it judges. Its steps are `plan`, the mint, `fetch`, `run`, the upload and `judge`, each a module of `harness/eval/` or a pinned action, in that order | Each run spends one model call for each case, so it runs when a cut is near, not on a timer; a report is a document of one Release (decision 0039) |
| The held-out credential | An App the Maintainer owns, installed on the home alone with `contents: read`. Its key is the secret `HELDOUT_APP_KEY` of the environment `factory-eval`, `main` alone, no reviewer. The mint narrows each token to the home and `contents: read`; it lives an hour and is revoked when the job ends. It is no Factory App, and `config/apps.json` does not hold it | The home is under an owner no org App reaches. A personal token is refused by the workflow standard and lives for days |
| The home's coordinates | `HELDOUT_OWNER`, `HELDOUT_REPO` and `HELDOUT_APP_CLIENT_ID` are secrets of `factory-eval`. No file in this repo names them | A step's log shows what it is given, and the log is public. GitHub masks a secret's value and never a variable's |
| The model credential | The organisation's secret `CLAUDE_CODE_OAUTH_TOKEN`, named by the `run` job and by the eval job's `run` step alone. It is not a secret of `factory-eval`. No branch policy narrows an organisation secret, unlike an environment's, so what holds it to the default branch is that only those two steps name it, that only the Maintainer has write, and that a fork's pull request is given no secret | The Maintainer's rule: the key is the organisation's. The eval job must call the model, or nothing is measured |
| One job, two credentials | Each credential is named by one step: the App's key by the mint, its token by `fetch`, the model's by `run`. No step is given both, and nothing above the steps is given either. The model runs with no tool (decision 0050) | A job that names an environment reads all its secrets (decision 0035), so the two are kept apart by step, and `tools/check_workflows.py` holds the text |
| The cases | `fetch` reads `{role}/{id}.json` for each id the manifest names, through the one transport, and writes the file only if its sha256 is the manifest's. They go into a directory of the runner's own outside the workspace, mode 0600, one at a time. Nothing a step prints is of a case, a Result or the home: counts and codes alone, and never what a step raised | The repo, its logs and its artifacts are public, and a held-out case that is seen is no longer held out |
| The report | `eval-report/1`: the Release and commit, the set by its count and the sha256 of its manifest, and each case by id and hash with its verdict and codes. No text. It is uploaded whatever the verdicts, and `judge` then fails the run unless `harness.eval.verdict` passes it | The gate reads the same function on the artifact it downloads. One test, in one place |
| A set of no case | `plan` prints `eval_set_empty` and ends the run before anything is minted or asked. No report is written, so the gate stays closed | A gate-deciding Intent may not serve without its eval set (FR-55) |

## Why

The design gives the eval job alone the credential that reads the held-out home (§4.9, §3.13), and the gate on `next` needs a report it can trust. Everything here is public, so the case must never reach a log or an artifact. And what is measured must be what runs (§3.14), so the model is called as `run` calls it. Two credentials in one job is the cost: they are kept apart by step, and the check holds the text so that no edit quietly joins them.

## Boundaries

| Boundary | Check |
|---|---|
| eval.yml is dispatched alone with its Release; one job on factory-eval; each credential named by one step alone; nothing above the job; the upload takes the report alone | `tests/test_evals.py::test_the_eval_workflow_names_each_credential_in_one_step_alone` |
| No other workflow names the eval job's environment, the home or its steps, in any case | `tests/test_evals.py::test_the_eval_workflow_names_each_credential_in_one_step_alone` |
| A held-out case is the bytes its manifest hashed or none, and one that could name another file or repo is not asked | `tests/test_adapters.py::test_a_held_out_case_is_its_hashed_bytes`, `tests/test_adapters.py::test_a_held_out_case_not_read_whole_says_why` |
| A set of no case ends the run before anything is minted | `tests/test_evals.py::test_a_set_of_no_case_ends_the_run_before_anything_is_minted` |
| Cases are kept outside the workspace, and only the report reaches it | `tests/test_evals.py::test_each_case_is_fetched_into_the_scratch_and_scored_and_only_the_report_reaches_the_workspace` |
| A step prints counts and codes, never what it raised | `tests/test_evals.py::test_a_step_says_counts_and_codes_and_never_what_it_raised` |
| The gate passes only this set's report on this commit for this Release | `tests/test_evals.py::test_the_gate_passes_only_this_sets_report_on_this_commit_for_this_release` |
| A report holds no text | `tools/check_examples.py` |
| A case is reviewed as `run` reviews a pull request | waiting on `harness/eval/run.py` |
