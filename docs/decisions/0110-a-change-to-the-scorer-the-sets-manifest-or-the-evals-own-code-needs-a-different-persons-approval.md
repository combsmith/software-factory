# 0110. A change to the scorer, the set's manifest or the eval's own code needs a different person's approval

Status: accepted. The Maintainer's ruling of 2026-11-01, as the Factory Builder relayed it, on "Evals: the scorer and the set are no input of the review, so a change to what grades it needs no person" (issue 471). It adds these paths to `docs/decisions/0052-a-change-to-a-model-lenss-own-inputs-needs-a-different-persons-approval.md`, and decides one sentence of `docs/decisions/0109-the-scorers-codes-are-in-the-public-report-and-the-judges-log.md` otherwise: a change to the scorer or the set is no longer his call alone, with no check.

## Decision

| What | Decided | Because |
|---|---|---|
| The paths | `pr-review`'s `lens_inputs` in `config/hooks.json` gain `tools/eval_result.py`, the scorer; `tools/jsonschema_lite.py`, which it and the job hold a case, a Result and a report to; `evals/pr-review/cases.json`, the set's manifest; `schemas/eval-case.schema.json`, `schemas/eval-report.schema.json`, `schemas/eval-set.schema.json` and `schemas/result.schema.json`; `adapters/heldout.py`, the only comparison of a case's bytes with the manifest's hash; and `.github/workflows/eval.yml`, the job | The eval measures the review, and its pass opens the Release's gate. A pull request that makes the scorer pass everything, or drops failing ids from the manifest, was read by the very reviewer the eval measures |
| What would be imported in their place | A directory of the name of each of `tools/eval_result.py`, `tools/jsonschema_lite.py`, `adapters/heldout.py`, `kernel/coverage.py` and `kernel/gate.py`, and, in the file's patterns, a package's first file or any Python file at the top of the repo, which the job imports before the standard library | Python takes a package before a module of its name, so a pull request could replace the scorer and leave its file as it is |
| Already on the list | `harness/eval/`, through `harness/`; `kernel/coverage.py`, which the scorer imports; `config/rubric-pr-review.json` and the review's prompt | They need no row |
| What it waits for | What decision 0052 says: every model Lens's review of the head, then an approval of it by a person with write access other than its author and last pusher. The machine user's never counts | The Maintainer's rule, for these paths too |
| When it starts | With the ruleset switch, "The ruleset switch: main requires the machine user's approval of the most recent commit, and slice 1's event is recorded" (issue 198), once the Kernel's Decision is what approves. Nothing runs the Kernel on a pull request before that: `.github/workflows/pass.yml` is called only by a poller that is not on main. Until the port for the base's settings is built, a pass reads this list at the Release's commit it checked out, so it holds once a Release holds these rows | The Maintainer's ruling says once the switch is live |
| Before the switch | Nothing changes for the eval work's pull requests: they merge as they do today, as changes to `harness/` have all along. A session is told of a change to the manifest at a stop, as of any Lens's input, and is asked nothing | The Factory Builder's instruction |
| What is left out | `tests/test_evals.py`, whose floor only a change to the manifest can reach; `evals/context/`, the context's test, which the review's eval does not read; the Release's own reading of the gate, `release/cut.py`, `release/rings.json`, `adapters/candidate.py`, `adapters/artifacts.py` and `.github/workflows/release.yml`, which are not the eval's code, though a change to them could open the gate as a passing eval does; and what the job shares with every Role, `adapters/github.py`, `kernel/derive.py`, `kernel/terms.py`, `release/current.py` and `tools/check_workflows.py` | The ruling names the scorer, the manifest and the eval's code. Listing what every Role shares would put a person on most of the Kernel's changes |

## Why

Decision 0052 keeps a model Lens from being the only judge of a change to what it is given and how its answer is taken. What grades its answer is the same case, one step on: decision 0109 said only that changing it after reading the codes was the Maintainer's call. Now the rule holds that, as it holds a rule path.

## Boundaries

| Boundary | Check |
|---|---|
| A change to each of these paths waits for a person after the model review, naming the pattern; the machine user's approval does not end the wait, and another person's does | `tests/test_decide.py::test_a_change_to_what_grades_the_review_waits_for_a_person` |
| What is left out does not wait | `tests/test_decide.py::test_a_change_to_what_grades_the_review_waits_for_a_person` |
| What the eval job imports is on the list, or left out above by name, and so is a package of a listed module's name | `tests/test_evals.py::test_what_the_eval_job_imports_is_on_the_reviews_list_or_left_out_by_name` |
| The Kernel is told of them from the base branch, as of every input of a model Lens | Waiting on `adapters/settings.py` |
| Each of these rows has a mutant that a test kills | `tools/mutants.py` |
