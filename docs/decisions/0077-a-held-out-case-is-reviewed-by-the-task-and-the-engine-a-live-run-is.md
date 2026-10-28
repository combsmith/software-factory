# 0077. A held-out case is reviewed by the Task and the Engine a live Run is

Status: accepted. The working ruling on "Workflows: eval.yml runs the review Intent's held-out cases and writes eval-report/1" (issue 309), rulings 4, 5 and 9, with its first and third amendments, for its second pull request. The Maintainer may overturn it in review. It adds to `docs/decisions/0053-the-eval-job-reads-the-held-out-home-with-the-maintainers-token-and-reports-hashes-and-codes-alone.md`, whose `run` step it builds.

## Decision

| What | Decided | Because |
|---|---|---|
| The Task | A case's Task is built by `from_admission` in `harness/task.py`, the function `task.build` builds a live Run's by once it has read the admission from the pass record. The admission is the case's own: its Role and Intent, and the content its facts name. The Task is given the case's facts and its diff, the checkout's `roles/pr-review.json` and configuration, no texts, no Findings, and a fresh Run id. Its Release is the one the dispatch names, held by `plan` | What is measured is what runs (design §3.14). The first amendment made the dispatch name the Release, so the Task carries that and not the commit |
| A case that is no Run's | A case whose facts do not name the content its diff is, the sha256 of the diff, or whose facts are no pull request's, builds no Task. It is `unreadable`, `not_this_set`, and nothing is asked of the model | The third amendment: a case's `content_id` is its diff's, as a live Run's is, so the diff reaching the model is the content the case stands for |
| The answer | Each Task is answered by `answer` in `harness/run.py`, the function the `run` job answers a live Run's by: a diff the Task cannot carry whole, or a rubric that cannot be read, fails before the CLI starts; otherwise the Engine runs it at the pin, with the tier's limits, `--tools ""` and the scrub. The Result is scored in process and never written | One path, so a fault of a live Run is a fault of a case |
| Time | The job runs on `ubuntu-24.04`, the runner the CLI's install is for, with a timeout of 120 minutes, both held by `tools/check_workflows.py`; the step spends at most 105 of them. It starts no case when the time left is less than that case's tier allows and the Engine's two reads of the CLI's version, and a case it does not start is `unreadable`, `unanswered`. The run fails, and does not hang | Ruling 9: a shorter timeout would end the job before the report is uploaded |
| A case's own fault | A case the review cannot be asked of is `unreadable` by its code; whatever else the review raises on a case is `unanswered`. The report of every case is written all the same, so the upload finds it and `judge` fails the run | Ruling 4: the report is always uploaded |
| The steps | `plan`, `fetch`, the CLI's install, `run`, the upload and `judge`, in that order: the install between `fetch` and `run`, which decision 0053's order did not yet hold | The first amendment |
| The CLI | `.github/workflows/eval.yml` installs the CLI between `fetch` and `run` by the block the Run's jobs install it by, word for word, given the Engine's pin in `config/harness.json` and its checksum in `CLI_CHECKSUMS`. The `run` step names the CLI's path beside the model's credential, and nothing else | The first amendment. The CLI a case is answered by is the CLI a Run calls |
| What runs beside both credentials | The vendor's CLI now runs in the one job that holds the held-out token and the model's credential, in separate steps: held by its sha256 at the pin, installed with the runner's own passwordless `sudo`, and given the model's credential alone. Decision 0053's list of what runs in that job, the pinned actions and this repo's code, gains it | The CLI must be the one a Run calls, and a Run's job installs it the same way |
| What reaches the CLI | The Engine's environment is its fixed names and the model's credential alone: nothing of the held-out home, its token or where it is, though the step's process holds what the runner gives every step | The scrub (decision 0050), held by a case's test |
| Verified on GitHub | Not here. Once this is on `main`, a dispatch from another branch is refused by `factory-eval`'s deployment branches, and a dispatch on `main` reads the home and uploads a report of hashes, verdicts and codes alone. A platform trial records both, its fixture holding hashes only. Then the story is done | Ruling 13: no session holds the home's credential, so the job's own runs are the evidence |
| The cost | Each dispatch spends one review-tier call for each of the set's cases, on the Factory's model credential, and the Maintainer dispatches it before a cut | Ruling 9 |

## Why

The first pull request built the steps that read, hash and judge. This one builds the step that asks the model, and it reuses the two
functions a live Run uses, rather than a copy of them, so that the eval set measures the Run the Release ships.

## Boundaries

| Boundary | Check |
|---|---|
| A case's Task is the one a live Run admitted for the same content is given, the CLI called as a live Run calls it, with nothing of the home | `tests/test_evals.py::test_a_case_is_reviewed_by_the_task_and_the_engine_a_live_run_is` |
| A case that names other content, or comes with too little time left, is not reviewed, and the step's time is held inside the job's | `tests/test_evals.py::test_a_case_that_names_other_content_or_comes_too_late_is_not_reviewed` |
| The report is written whatever a case raised | `tests/test_evals.py::test_the_run_step_writes_the_report_whatever_a_case_raised` |
| `.github/workflows/eval.yml`'s install is the Run's jobs' block at the pin, between the fetch and the model's step, and the model's step names the CLI's path | `tests/test_evals.py::test_the_eval_workflow_names_each_credential_in_one_step_alone` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
