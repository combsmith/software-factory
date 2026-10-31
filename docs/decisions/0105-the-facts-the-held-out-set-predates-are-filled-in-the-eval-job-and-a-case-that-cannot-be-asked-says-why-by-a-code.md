# 0105. The facts the held-out set predates are filled in the eval job, and a case that cannot be asked says why by a code

Status: accepted. The Maintainer's ruling of 2026-10-31, after the first eval, run 41201337899 on the commit 743e761, read all 44 cases as `not_this_set` with no model call: fill the defaults in the eval job, and leave the private set untouched. It adds to `docs/decisions/0078-a-held-out-case-is-reviewed-by-the-task-and-the-engine-a-live-run-and-its-report-tells-nothing-it-expected.md` and `docs/decisions/0053-the-eval-job-reads-the-held-out-home-with-the-maintainers-token-and-reports-hashes-and-codes-alone.md`.

## Decision

| What | Decided | Because |
|---|---|---|
| The cause | Since the set was made, at d556992, facts/1 has come to require `last_reopened_at`, `expired_reviews` and each thread's `ruling`. The eval-case schema's `facts` is facts/1, and `harness.eval.assess` holds every case to it before anything else reads the case, so each failed there, as `not_this_set`. Read from the code and the schema alone: nobody here may read a case. The repo's own example of that commit fails today's schema on those three fields and on nothing else | A required field added for the live path silently refused the whole set, which nothing tested |
| The table | `FACTS_THE_SET_PREDATES` and `THREAD_FIELDS_THE_SET_PREDATES`, in `harness/eval/__init__.py`, name each field with its default and what it means: never reopened, `null`; no Lens review past retention, `[]`; a Lens that decided nothing of its Finding, `null` | The defaults say what is true of a pull request of which nothing more is known |
| What a default costs | A case cannot exercise one of these fields until it is issued again with it: an approval from before a reopening, a review asked for again after retention, a ruling on a thread | The set was written before they existed. The eval measures the review of the change, which none of them is |
| Where it is filled | In the eval job alone: `assess` fills a case's facts as it reads it, before anything else does, so that the review and the scorer both read the filled case. A field a case gives is its own. `harness/task.py`'s `from_admission` and the live path do not change, and go on refusing such facts | A live Run's facts are read now, and a field missing from them is a fault to refuse |
| The guard | A test holds the facts as the set was made, the repo's own example at d556992, filled by the table, to today's schema. A field made required later fails it until it has a row, or the set is issued again. Each row must be of a field the schema requires and the snapshot lacks | The fault this record mends was silent, and cost a dispatch to find |
| Telling the causes apart | A case whose facts are still no `facts/1` after the fill is `unreadable`, `facts_not_current`. The job then reads, before the Task is built, what would refuse it: facts read short, `facts_read_short`; a diff empty or that cannot be encoded, `diff_unreadable`; a diff that is not its `content_id`, `diff_not_content`; a last pusher that is null or no login, which facts/1 allows and `task/1` does not, `pusher_unnamed`; and, once the Task is built, a diff over the Kernel's bound, `diff_not_whole`, which read before as a case the reviewer failed. Nothing is asked of the model. `harness/task.py` is untouched and refuses them as before | A set that fails on any of these says why, so that no dispatch is spent finding out, and each is the owner's to mend in the home. If a whole set is `diff_not_content`, its facts and diffs were written apart |
| Codes alone | Each is a code: no field's name, value or diff is in the report or the log. `facts_not_current` does not say which field | The report is public, and a code rather than a sentence. No session may read a case to say more |
| What `not_this_set` still covers | A case of another id, Role or Intent, and what the Task's schema alone refuses: a repo's name outside `task/1`'s narrower pattern. Tracing `task/1` against facts/1 found nothing else a case could trip | One code for what is left |
| The manifest and the fill | The id and hash are read of the bytes the home gives, at the fetch, before any fill, and the fill is of a copy in memory: the scratch holds what the manifest hashed. A case the fill would read alike is still a changed case | Otherwise a filled case could read as a changed one, or a changed one pass (the Factory Builder's condition) |

## Why

The live path and the held-out set share a schema, so the set is measured by the Task a live Run is given (0078). But the set is frozen, and the schema is not: each field the Kernel came to need made every case unreadable, with no failure until the job ran.

## Boundaries

| Boundary | Check |
|---|---|
| The facts as the set was made, filled by the table, pass today's schema; each row is of a field the schema requires and the snapshot lacks; a row taken away fails | `tests/test_evals.py::test_the_facts_the_set_was_made_with_read_as_todays_once_filled` |
| A case of the set's time reaches the review filled, and is scored; a field it gives is kept; two cases share no default; the live path still refuses such facts | `tests/test_evals.py::test_a_case_the_set_predates_is_filled_where_it_is_read_and_the_live_path_is_not` |
| A case whose facts are still no `facts/1` is `facts_not_current`, asks nothing, and names no field; one of another set, or with no facts, is `not_this_set` | `tests/test_evals.py::test_a_case_whose_facts_are_not_current_says_so_by_a_code_alone` |
| Each fault that would refuse a case's Task says so by its own code, asks nothing, and names nothing of the case | `tests/test_evals.py::test_what_would_refuse_a_cases_task_says_so_by_a_code_of_its_own` |
| A diff over the bound is `diff_not_whole`, and asks nothing | `tests/test_evals.py::test_a_diff_over_the_bound_says_so_and_asks_nothing` |
| The manifest's hash is of a case's raw bytes, which the fill never touches, and a case changed to read as filled is `hash_differs` | `tests/test_evals.py::test_the_manifest_holds_a_cases_raw_bytes_and_the_fill_never_touches_them` |
| A report that names a field in its code is refused | `examples/invalid/eval-report.names-a-field-in-its-code.json` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
