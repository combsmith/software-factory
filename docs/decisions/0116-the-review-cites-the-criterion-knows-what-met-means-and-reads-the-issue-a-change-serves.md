# 0116. The review cites the criterion, knows what `met` means, and reads the issue a change serves

Status: accepted. The Builder's ruling of 2026-11-01, on eval run 41329046436 on the commit 14a3b6e: 3 pass, 19 `criterion_not_met`, 10 `finding_uncited`, 6 `finding_elsewhere` and 4 `finding_not_raised`, of 42. The Maintainer ruled the same day that the scorer stays as it is, `met` only on a clean case and no change to the pass rule, so the fix is the Role's.

## Decision

| What | Decided | Because |
|---|---|---|
| Citing | `roles/pr-review/prompt.md` tells the reviewer to cite the criterion a problem falls under, the nearest that fits, with its severity and category, and none only when no criterion reaches it. PR-3's words in `config/rubric-pr-review.json` become "The change does what it means to, with no logic error, and new behaviour has a test that would fail without it", its evidence the diff. No id, category or severity moves, and the rubric's version is 2 | The prompt alone moved nothing: canary run 41325894979 cited 2 of 6, as the prompt before it did. "New behaviour has a test" did not read as covering a logic error, and no criterion did. With both, canary run 41331131787 cited 6 of 6. A Finding that cites a criterion takes its severity and category (0095), so those differences go with it |
| `met` and `not_applicable` | `met` is the change read against the criterion and holding, which includes a change that gives it nothing to break. `not_applicable`, with a code, is only for what the Task does not hold. A criterion that could not be judged is still not `met` | The model answered `not_applicable`, `no_new_behaviour_introduced`, on a clean change where the scorer asks `met`. Run 41331131787: a docstring change reads `met` on PR-3, 3 of 3 |
| An issue's text, live | `adapters/texts.py` reads the body of each issue a pull request serves, by the rule `adapters/acceptance.py` holds it to, and `harness/read.py` writes it among the Task's inputs. It is the reader's `read:task.issue_texts`, a grant `config/apps.json` already holds. A text's class is read from who wrote it, and an outsider's stays `outside`. An issue with no body has no text, and what cannot be read whole stops the step as `facts_unreadable` | PR-1 asks whether a change does what its issue asks, and a Task of the diff alone could never judge it, in a live Run or a case |
| An issue's text, in a case | `eval-case/1` takes an optional `issue`, its number, who wrote it and its body, and `harness/eval/run.py` gives it to the Task as the id and class a live Run's has. A case without one is reviewed on its diff alone. The set's cases hold none yet: adding them is a change to the private home, which is the Maintainer's | Run 41331131787: a clean change expected `met` on PR-1 passes 3 of 3 with its issue, and fails 3 of 3 without it, `not_applicable`, as it should |
| What does not change | `tools/eval_result.py` is not touched, nor the set | The gate is the Maintainer's. These cases are the repo's own and synthetic, so nothing here was fitted to a held-out case. Whether a change after reading the codes fits the prompt to the set is his call (0109), and he asked for this one |
| Its limits | The issue is read when the Run is, and the Decision does not hold it to a content id, so an issue edited between admission and the read is the text the Task holds. Nothing here has run with the reader's real token: its read is the one `adapters/acceptance.py` makes for a bound issue, and the first live Run shows it. Canary runs measure the repo's own synthetic cases, three runs of each | Said so that a green canary is not read as more than it holds |

## Why

Run 41329046436 showed the reviewer judging well and answering in the wrong form: it found a fault at or near the place in about 16 of 20, and raised a false alarm in about 1 of 22. A reviewer that finds a bug and cites nothing, or that cannot be given the issue it is asked about, fails whatever it judges. Those are faults of what the Role is told and given, and a live Run has them too.

## Boundaries

| Boundary | Check |
|---|---|
| The review is told to cite and what `met` means; a logic error falls under PR-3, whose evidence the Task holds; no id, category or severity moves | `tests/test_evals.py::test_the_review_is_told_to_cite_and_what_met_means` |
| A Task is given the body of each issue the change serves, the writer read from the issue, the bound one where a branch binds it; an issue with no body has no text | `tests/test_adapters.py::test_a_task_is_given_the_body_of_each_issue_the_change_serves` |
| What cannot be read whole builds no Task | `tests/test_adapters.py::test_what_cannot_be_read_whole_builds_no_task` |
| The reader writes the issues' text among the Task's inputs | `tests/test_steps.py::test_the_reader_writes_the_tasks_inputs` |
| A case's issue reaches its Task as a live Run's does, its class read from who wrote it | `tests/test_evals.py::test_a_case_that_holds_its_issue_gives_it_to_the_task_as_a_live_run_is` |
| An issue with no body is no case | `examples/invalid/eval-case.an-issue-with-no-body.json` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
