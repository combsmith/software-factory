# 0094. The eval job holds a set's split where its cases are, and no count of a kind is public

Status: accepted. The Factory Builder's ruling of 2026-10-30 on issue 365, "Evals: the held-out manifest holds its Finding and right-change counts, so the cutover's split is held": no count of a kind is public, in place of the counts that issue's checklist asks the manifest to hold, after the reads of an earlier shape of this pull request. The Maintainer may overturn it in review. It adds to `docs/decisions/0078-a-held-out-case-is-reviewed-by-the-task-and-the-engine-a-live-run-and-its-report-tells-nothing-it-expected.md`, whose job and public report it extends, and holds the split that `docs/decisions/0010-built-greenfield-cut-over-one-family-at-a-time.md`'s cutover waits on.

## Decision

| What | Decided | Because |
|---|---|---|
| What is public of a set's kinds | Nothing but one word of the whole set: no file in this repo, no report and no log holds how many of its cases expect a Finding or how many a criterion met. The manifest stays as it was, its count and each case's id and hash, and the review Intent's set is held to 40 cases at least by the test 0010 names | The counts were first written in the manifest. With them public, each change to the set tells how the cases it names relate: a swap that keeps the counts says two cases are of one kind, a removal of one of each says they differ, and two allowed changes in a row can prove one case's kind (the security pass and Muse, each on its own). The answer key could be built from public manifests alone |
| Where the split is held | In the eval job, where the cases are: `harness.eval.split_ok` reads the verdict each fetched case expects, and the set must hold `KIND_LEAST`, 20, of each kind, the split of issue 183, "The review Intent's held-out eval set, from the proof of concept's merged-then-reverted pull requests" | The job is the one place that may read a case, and reading them there, each run, the split cannot drift from the set |
| What the report says | `eval-report/1` takes `split_ok`: true, false, or null where a case was not read or its answer is no kind. It holds neither count, and no field of the report is per kind | A run with a case not read fails by that case anyway |
| How it closes the gate | `harness.eval.verdict`, which the job's `judge` and the Release's gate both read the report with, refuses a report whose `split_ok` is not true, as `eval_split_short`, a code alone, after every case's own verdict. So the run fails with the code, its report uploaded all the same, and the gate is closed twice over: `adapters/candidate.py` takes only a dispatch that concluded `success`, and then reads the report by `verdict` | The gate reads the verdict's word, and a report is uploaded whatever the verdicts, so the word itself must refuse |
| What the Maintainer gave | His counts for the review Intent's set are not written here | Nothing public may hold them, and the job reads the set itself |
| The counts already public | An earlier shape of this change wrote the review set's split in the manifest and in the pull request's commits and text, on a public repo, for a time, and that cannot be fully erased. So the set's current ids are treated as having a known split: the next change to the set re-ids every case in the home, which is the Maintainer's act when it comes | With its split known, a change to the set named by id would tell the kind of each case it names, as above. New ids name no case the old split spoke of |
| Accepted | `split_ok`, the public count and `KIND_LEAST` together bound each kind, and a set of exactly twice `KIND_LEAST` tells both counts. At that margin the word can also tell how cases relate: someone who can land a manifest on main and dispatch the job could remove a case and read the word. Decision 0053 already trusts main, and each probe is a merged change and a paid dispatch. Older and stronger is the report's per-case verdict, filed as issue 430, "Evals: the public report's per-case verdicts can publish each case's kind" | The word must be public for the gate to read it, and the job's code would say as much. The per-case verdict is the Maintainer's to rule on, and this change does not make it worse |

## Why

Muse's read of the merged diff of pull request 363, "Evals: the review Intent's held-out set has its 44 cases, and the cutover's rule is held", found the split stated but not held: a set of one kind would pass, and a reviewer that approves everything could then pass the gate. Holding it in the manifest traded that for a slower leak of the answer key, so it is held where the cases are, and the manifest stays as it was.

## Boundaries

| Boundary | Check |
|---|---|
| A set short of `KIND_LEAST` of a kind, read from the cases fetched, fails the run by a code alone, its report uploaded; neither the log nor the report holds a count of a kind; a case not read, or of no kind, says nothing | `tests/test_evals.py::test_a_set_short_of_a_kind_fails_the_run_and_closes_the_gate_saying_no_count` |
| The gate is closed by a report whose `split_ok` is false, by one that cannot say, by one with no such word, and by a run that did not succeed | `tests/test_release_step.py::test_the_eval_gate_is_closed_by_anything_not_read_whole_or_not_passed` |
| A report that carries a count of a kind is refused, beside its word or as its word | `examples/invalid/eval-report.carries-a-count-of-a-kind.json`, `examples/invalid/eval-report.a-count-in-its-word.json` |
| The review Intent's set holds 40 cases at least | `tests/test_evals.py::test_the_review_intents_eval_set_has_its_cases` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
