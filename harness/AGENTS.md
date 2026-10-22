# harness/

The Harness: the jobs that carry one Run. `task.py` builds the Task from the Decision that admitted the Run, `engine.py` runs the vendor's CLI on it and takes the Result from its answer, and `run.py` is the `run` job, which writes the Result and its
digest and nothing else of the model. `apply.py` is what the `apply` job does with that Result: it reads the item again, refuses what may not be written, writes the Effects with a token narrowed to them, and records only what it read back. The model
is given no tool, and the CLI no secret but the one under its own name. Every test drives a stand-in for the CLI: the first live Run is the workflows' and the Release's. `eval/` is the eval job's steps, `factory / eval`: the held-out set run on the
commit it judges, each case read into a scratch outside the workspace, scored, and reported by hashes, verdicts and codes alone (decision 0053; its rules are `evals/AGENTS.md`'s). `approve.py` is the approving act, a Run with no Engine: through the
machine user's token alone it approves the commit it read, only if the Kernel asked again still wants it (decision 0055).

Not built yet, by the stories that hold their rules: verify.py, push.py, eval/run.py.

| Rule | Held by |
|---|---|
| A Task is built from the Decision that admitted its Run, and nothing else | `tests/test_harness.py::test_a_task_is_built_from_the_decision_that_admitted_its_run` |
| A Run no Decision admitted is refused | `tests/test_harness.py::test_a_run_no_decision_admitted_finds_none_and_does_nothing` |
| A text's trust class is read from who wrote it, never from the text | `tests/test_harness.py::test_each_text_is_labelled_by_who_wrote_it_never_by_the_text` |
| A Task keeps each text whole or leaves it out, the Maintainer's first, and says what it left out and how much | `tests/test_harness.py::test_a_task_says_what_it_left_out_and_how_much` |
| The CLI is given exactly the named environment: the scrub set, the credential under its one name, no other secret | `tests/test_harness.py::test_the_cli_is_given_exactly_the_named_environment_and_the_one_credential` |
| With no credential, nothing is asked | `tests/test_harness.py::test_no_credential_asks_nothing` |
| The CLI is given no tool, the Task as data after a fixed instruction, and the Task's limits | `tests/test_harness.py::test_the_cli_is_given_no_tool` |
| A Task too long for one argument is refused before the CLI starts | `tests/test_harness.py::test_a_task_too_long_for_one_argument_is_refused_before_the_cli_starts` |
| An issue's Run is found among the issues | `tests/test_harness.py::test_an_issues_run_is_found_among_the_issues` |
| The CLI is handed `result/1` resolved, with the Harness's fields removed and status and Effects narrowed | `tests/test_harness.py::test_the_cli_is_handed_result_1_resolved_and_narrowed` |
| The CLI's version is held to the pin before and after the call | `tests/test_harness.py::test_the_version_is_held_before_and_after_the_call` |
| The Harness fills `release` and `usage` from the CLI's own answer, and keeps none of the model's prose | `tests/test_harness.py::test_a_result_the_engine_wrote_is_filled_and_kept` |
| An answer that does not validate is a `failed` Result, `result_invalid`, with empty lists | `tests/test_harness.py::test_an_answer_that_does_not_validate_is_no_result` |
| A CLI that fails or runs past its time is a `failed` Result | `tests/test_harness.py::test_a_cli_that_fails_or_runs_past_its_time_is_a_failed_result` |
| The `run` job writes the Result and its digest; the log carries the digest alone | `tests/test_harness.py::test_the_job_writes_the_result_and_its_digest_and_nothing_else`, `tests/test_harness.py::test_the_log_carries_the_digest_alone` |
| The CLI starts in an empty directory, with nothing on its input and only its environment | `tests/test_harness.py::test_the_cli_starts_in_an_empty_directory_with_only_its_environment` |
| `apply` writes nothing on an item closed, held, paused, moved or no longer admitted for the Run, the Kernel asked again with the Run left out | `tests/test_apply.py::test_a_change_under_the_run_writes_nothing_and_is_superseded` |
| `apply` writes nothing for a Result not the Run's, not completed or uncovered | `tests/test_apply.py::test_a_result_not_the_runs_or_not_completed_writes_nothing`, `tests/test_apply.py::test_an_uncovered_result_writes_nothing` |
| `apply` refuses an Effect not permitted, a thread off the item, or a Finding posted other than once or out of place | `tests/test_apply.py::test_effects_the_task_does_not_permit_or_findings_posted_other_than_once_write_nothing` |
| A Disposition gives one half, the one its Role may make, on a Finding the Task lists; a `security` thread is never resolved on declined or deferred | `tests/test_apply.py::test_a_disposition_gives_one_half_and_only_the_half_its_role_may_make` |
| A review is a comment on the admitted commit; a check run is named by `apply`; a Finding is written from its surface | `tests/test_apply.py::test_a_result_on_the_item_as_admitted_is_written_and_recorded_from_what_was_read_back` |
| An Effect is claimed only from what was read back | `tests/test_apply.py::test_an_effect_is_claimed_only_from_what_was_read_back` |
| The Result is taken by the digest `run` reported, and held to its schema | `tests/test_apply.py::test_a_result_is_taken_by_the_digest_run_reported_and_held_to_its_schema` |
| A Result is held to the Decision that admitted its Run | `tests/test_apply.py::test_what_a_result_is_held_to_is_the_decision_that_admitted_its_run` |
| Nothing is minted for a refused Result, and the token is revoked whatever happens | `tests/test_apply.py::test_nothing_is_minted_for_a_refused_result_and_the_token_is_revoked_whatever_happens` |
| The approving act sends one write, the approval of the commit it read, and claims only what it reads back | `tests/test_approve.py::test_the_act_sends_one_write_and_it_is_the_approval` |
| It approves only through the approver's token, for a Decision that issued the approval, what the Kernel still wants | `tests/test_approve.py::test_the_act_approves_only_what_the_kernel_asked_again_still_wants` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
