# 0099. The eval job holds a set's split where its cases are, since the repo cannot hold the counts true

Status: replaced by `docs/decisions/0109-the-scorers-codes-are-in-the-public-report-and-the-judges-log.md`.

## Decision

| What | Decided | Because |
|---|---|---|
| Where a set's split is held | In the eval job, where the cases are: `harness.eval.split_ok` reads the verdict each fetched case expects, and the set must hold `KIND_LEAST`, 20, of each kind, the split of issue 183, "The review Intent's held-out eval set, from the proof of concept's merged-then-reverted pull requests" | The job is the one place that may read a case. Read there, each run, the split cannot drift from the set |
| What the repo holds of a set's kinds | No count, in place of the counts the first of those issues' checklist asks the manifest to hold. The manifest stays as it was, its count and each case's id and hash, and the review Intent's set is held to 40 cases at least by the test 0010 names | The check belongs where the cases are, and the repo cannot hold the counts true: a session here cannot read a case, so a count written here could only be taken on trust |
| What the report says | `eval-report/1` takes `split_ok`: true, false, or null where a case was not read or its answer is no kind. It holds neither count | The gate needs one word of the whole set, and nothing more |
| How it closes the gate | `harness.eval.verdict`, which the job's `judge` and the Release's gate both read the report with, refuses a report whose `split_ok` is not true, as `eval_split_short`, a code alone, after every case's own verdict. So the run fails with the code, its report uploaded all the same, and the gate is closed twice over: `adapters/candidate.py` takes only a dispatch that concluded `success`, and then reads the report by `verdict` | The gate reads the verdict's word, and a report is uploaded whatever the verdicts, so the word itself must refuse |
| What is not secret | A case's kind by its id, and so the split. The report keeps each case's id, verdict and code, as 0078 has it. An id's kind is useless without the case's content, which stays in the private home; and the reviewer cannot use it, since its Task holds a fresh Run id, the diff and the facts, and no case id, and it runs with `--tools ""` (the Maintainer's ruling named above, which adds that a case whose content reaches someone who should not have it is spent). 0078's rule stands, one code whatever the scorer said, since a scorer's code could tell the category, severity or place a case expects, which are its content; its wording that the codes would assemble an answer key does not | 0094 called a public count and the ids a change adds or removes a leak of the answer key. The Maintainer's ruling speaks of the per-case verdict, and calls the Builder's description of that as the answer key overstated. The Factory Builder reads the same of the counts: a kind told of an id tells nothing without the content |
| What was public | The review set's split stood on pull request 413, "Evals: the job holds a set's split where its cases are, and no count of a kind is public", for a time, and can still be read in its history. That is harmless for the same reason, and nothing follows from it: a change to the set need not give its cases new ids | On that reading, 0094's rule that the next change to the set re-ids every case protects nothing, so the Factory Builder withdraws it |

## Why

Muse's read of the merged diff of pull request 363, "Evals: the review Intent's held-out set has its 44 cases, and the cutover's rule is held", found the split stated but not held: a set of one kind would pass, and a reviewer that approves everything could then pass the gate. That is what this holds. It holds it in the job because that is where the cases are.

## Boundaries

| Boundary | Check |
|---|---|
| A set short of `KIND_LEAST` of a kind, read from the cases fetched, fails the run by a code alone, its report uploaded; neither the log nor the report holds a count of a kind; a case not read, or of no kind, says nothing | `tests/test_evals.py::test_a_set_short_of_a_kind_fails_the_run_and_closes_the_gate_saying_no_count` |
| The gate is closed by a report whose `split_ok` is false, by one that cannot say, by one with no such word, and by a run that did not succeed | `tests/test_release_step.py::test_the_eval_gate_is_closed_by_anything_not_read_whole_or_not_passed` |
| A report that carries a count of a kind is refused, beside its word or as its word | `examples/invalid/eval-report.carries-a-count-of-a-kind.json`, `examples/invalid/eval-report.a-count-in-its-word.json` |
| The review Intent's set holds 40 cases at least | `tests/test_evals.py::test_the_review_intents_eval_set_has_its_cases` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
