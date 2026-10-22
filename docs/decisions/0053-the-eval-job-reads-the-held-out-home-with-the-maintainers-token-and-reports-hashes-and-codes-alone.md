# 0053. The eval job reads the held-out home with the Maintainer's token, and reports hashes, verdicts and codes alone

Status: accepted. A working ruling of 2026-10-21 on "Workflows: eval.yml runs the review Intent's held-out cases and writes eval-report/1" (issue 309), with its amendments, which the Maintainer may overturn in review; the rows of the two credentials are his choices of 2026-10-22. It decides one row of design §4.9's credentials table otherwise, and the form of the eval gate that the ruling on "Release: cut, promote and roll back the Factory's own Releases" (issue 197) reads.

## Decision

| What | Decided | Because |
|---|---|---|
| The job | The workflow eval.yml, `factory / eval`, on `workflow_dispatch` alone with one input, the Release it judges, run from the default branch at the commit it judges. Its steps are `plan`, `fetch`, `run`, the upload and `judge`, each a module of `harness/eval/` or a pinned action, in that order | Each run spends one model call for each case, so it runs when a cut is near, not on a timer; a report is a document of one Release (decision 0039) |
| The held-out credential | A fine-grained personal token of the Maintainer's own account, scoped to the home alone, `contents` read-only and `metadata` read, with an expiry. It is the secret `HELDOUT_TOKEN` of the environment `factory-eval`, `main` alone, no reviewer. Only eval.yml's `fetch` step names it, and that step sends nothing but GETs with it. It is the one personal token the workflow standard names as an exception | His choice: "For the holdout access, let's just use my account." The home is under his account, which no org App reaches |
| The trade | The token is not minted for each job and does not lapse when the job ends: it lives until its expiry or until he revokes it, and a token that leaked would read the home until then. Its age and expiry are read by "Credentials: each stored credential's age read, and one alert near its limit (L-37)" (issue 305), when it is built; until then he tracks them | An App of his own would give hour-long tokens, at the cost of registering one; he chose the token |
| The home's coordinates | `HELDOUT_OWNER` and `HELDOUT_REPO` are secrets of `factory-eval`. No file in this repo names them | A step's log shows what it is given, and the log is public. GitHub masks a secret's value and never a variable's |
| The model credential | The organisation's secret `CLAUDE_CODE_OAUTH_TOKEN`, its repository access this repo alone, with no copy in any environment. Only the `run` job and the eval job's `run` step name it, and no other workflow file may | The Maintainer's choice of 2026-10-22, "Org secret, this repo only". The eval job must call the model, or nothing is measured |
| The risk he accepted | No branch policy narrows an organisation secret, as one narrows an environment's: a workflow on any branch of this repo can read it. A fork's pull request is given no secret; write here is held by the Maintainer and one member of the org, through the org's default permission, so a branch either pushes could read it | It is his to accept, and he has; what holds it is who can push, and that the check refuses every other naming in the workflows on the default branch |
| One job, two credentials | Each credential is named by one step: the Maintainer's token by `fetch`, the model's by `run`. No step is given both, and nothing above the steps is given either. The model runs with no tool (decision 0050) | A job that names an environment reads all its secrets (decision 0035), so the two are kept apart by step, and `tools/check_workflows.py` holds the text |
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
| No workflow but eval.yml and the `run` job's names the model credential, and none but eval.yml's `fetch` names the Maintainer's token; the token sends GETs alone | `tests/test_evals.py::test_the_eval_workflow_names_each_credential_in_one_step_alone`, `tests/test_evals.py::test_the_fetch_step_takes_its_token_from_its_environment_alone` |
| A held-out case is the bytes its manifest hashed or none, and one that could name another file or repo is not asked | `tests/test_adapters.py::test_a_held_out_case_is_its_hashed_bytes`, `tests/test_adapters.py::test_a_held_out_case_not_read_whole_says_why` |
| A set of no case ends the run before anything is minted | `tests/test_evals.py::test_a_set_of_no_case_ends_the_run_before_anything_is_minted` |
| Cases are kept outside the workspace, and only the report reaches it | `tests/test_evals.py::test_each_case_is_fetched_into_the_scratch_and_scored_and_only_the_report_reaches_the_workspace` |
| A step prints counts and codes, never what it raised | `tests/test_evals.py::test_a_step_says_counts_and_codes_and_never_what_it_raised` |
| The gate passes only this set's report on this commit for this Release | `tests/test_evals.py::test_the_gate_passes_only_this_sets_report_on_this_commit_for_this_release` |
| A report holds no text | `tools/check_examples.py` |
| A case is reviewed as `run` reviews a pull request | waiting on `harness/eval/run.py` |
