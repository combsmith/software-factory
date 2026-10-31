# 0105. The facts the held-out set predates are filled in the eval job, and a case they cannot mend says so

Status: accepted. The Maintainer's ruling of 2026-10-31, after the first eval, run 41201337899 on the commit 743e761, read all 44 cases as `not_this_set` with no model call: fill the defaults in the eval job, and leave the private set untouched. It adds to `docs/decisions/0078-a-held-out-case-is-reviewed-by-the-task-and-the-engine-a-live-run-and-its-report-tells-nothing-it-expected.md` and `docs/decisions/0053-the-eval-job-reads-the-held-out-home-with-the-maintainers-token-and-reports-hashes-and-codes-alone.md`.

## Decision

| What | Decided | Because |
|---|---|---|
| The cause | Since the set was made, at d556992, facts/1 has come to require `last_reopened_at`, `expired_reviews` and each thread's `ruling`. The eval-case schema's `facts` is facts/1, and `harness.eval.assess` holds every case to it before anything else reads the case, so each failed there, as `not_this_set`. Read from the code and the schema alone: nobody here may read a case. The repo's own example of that commit fails today's schema on those three fields and on nothing else | A required field added for the live path silently refused the whole set, which nothing tested |
| The table | `FACTS_THE_SET_PREDATES` and `THREAD_FIELDS_THE_SET_PREDATES`, in `harness/eval/__init__.py`, name each field with its default and what it means: never reopened, `null`; no Lens review past retention, `[]`; a Lens that decided nothing of its Finding, `null` | The defaults say what is true of a pull request of which nothing more is known |
| What a default costs | A case cannot exercise one of these fields until it is issued again with it: an approval from before a reopening, a review asked for again after retention, a ruling on a thread | The set was written before they existed. The eval measures the review of the change, which none of them is |
| Where it is filled | In the eval job alone: `assess` fills a case's facts as it reads it, before anything else does, so that the review and the scorer both read the filled case. A field a case gives is its own. `harness/task.py`'s `from_admission` and the live path do not change, and go on refusing such facts | A live Run's facts are read now, and a field missing from them is a fault to refuse |
| The guard | A test holds the facts as the set was made, the repo's own example at d556992, filled by the table, to today's schema. A field made required later fails it until it has a row, or the set is issued again. Each row must be of a field the schema requires and the snapshot lacks | The fault this record mends was silent, and cost a dispatch to find |
| Telling the causes apart | A case whose facts are still no `facts/1` after the fill is `unreadable`, `facts_not_current`, and nothing is asked of the model. Every other refusal keeps its code. It is a code alone: no field's name is in the report or the log | A code rather than a sentence. It does not say which field: the Maintainer reads the case against the schema at his terminal, and no session may |
| What `not_this_set` still covers | A case of another id, Role or Intent, and what `harness.task.from_admission` refuses after the schema: facts read short (`complete`), and a diff that is empty, is not the `content_id`'s, or cannot be encoded. A next dispatch may fail on one of these, or on `answer_off_rubric`, at no model cost for that case. They are not told apart here | The Maintainer's ruling keeps those codes |

## Why

The live path and the held-out set share a schema, so the set is measured by the Task a live Run is given (0078). But the set is frozen, and the schema is not: each field the Kernel came to need made every case unreadable, with no failure until the job ran.

## Boundaries

| Boundary | Check |
|---|---|
| The facts as the set was made, filled by the table, pass today's schema; each row is of a field the schema requires and the snapshot lacks; a row taken away fails | `tests/test_evals.py::test_the_facts_the_set_was_made_with_read_as_todays_once_filled` |
| A case of the set's time reaches the review filled, and is scored; a field it gives is kept; two cases share no default; the live path still refuses such facts | `tests/test_evals.py::test_a_case_the_set_predates_is_filled_where_it_is_read_and_the_live_path_is_not` |
| A case whose facts are still no `facts/1` is `facts_not_current`, asks nothing, and names no field; one of another set, or with no facts, is `not_this_set` | `tests/test_evals.py::test_a_case_whose_facts_are_not_current_says_so_by_a_code_alone` |
| A report that names a field in its code is refused | `examples/invalid/eval-report.names-a-field-in-its-code.json` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
