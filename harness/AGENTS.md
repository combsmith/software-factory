# harness/

The Harness: the jobs that carry one Run. `task.py` builds the Task from the Decision that admitted the Run, `engine.py` runs the CLI on it, with no tool and no secret but its own, and `run.py` writes the Result and its digest alone. `apply.py` reads the item
again, refuses what may not be written, writes the Effects with a token narrowed to them and records what it read back; `approve.py` is the approving act, a Run with no Engine, through the machine user's token alone (decision 0055). Steps: `read.py`, the
reader's; `verify.py`; `apply_step.py` and `outcome.py`; `approve_step.py`; `reread.py`, the item read again; `steps.py`, their files. `eval/` is the eval job's steps (decision 0053; rules in `evals/AGENTS.md`). Every test drives a stand-in for the CLI.
Not built yet, by the stories that hold their rules: push.py.

| Rule | Held by |
|---|---|
| A Task is built from the Decision that admitted its Run, and nothing else | `tests/test_harness.py::test_a_task_is_built_from_the_decision_that_admitted_its_run` |
| A Run no Decision admitted is refused; with no credential, nothing is asked | `tests/test_harness.py::test_a_run_no_decision_admitted_finds_none_and_does_nothing`, `tests/test_harness.py::test_no_credential_asks_nothing` |
| A text's trust class is read from who wrote it, never from the text | `tests/test_harness.py::test_each_text_is_labelled_by_who_wrote_it_never_by_the_text` |
| A Task keeps each text whole or leaves it out, the Maintainer's first, and says what it left out and how much | `tests/test_harness.py::test_a_task_says_what_it_left_out_and_how_much` |
| The CLI is given exactly the named environment: the scrub set, the credential under its one name, no other secret | `tests/test_harness.py::test_the_cli_is_given_exactly_the_named_environment_and_the_one_credential` |
| The CLI is given no tool, the Task as data after a fixed instruction, and the Task's limits | `tests/test_harness.py::test_the_cli_is_given_no_tool` |
| A Task too long for one argument is refused before the CLI starts | `tests/test_harness.py::test_a_task_too_long_for_one_argument_is_refused_before_the_cli_starts` |
| An issue's Run is found among the issues; an Effect is claimed only from what was read back | `tests/test_harness.py::test_an_issues_run_is_found_among_the_issues`, `tests/test_apply.py::test_an_effect_is_claimed_only_from_what_was_read_back` |
| The CLI is handed `result/1` resolved, with the Harness's fields removed and status and Effects narrowed | `tests/test_harness.py::test_the_cli_is_handed_result_1_resolved_and_narrowed` |
| The CLI's version is held to the pin before and after the call; a step runs as its checkout's one Release tag | `tests/test_harness.py::test_the_version_is_held_before_and_after_the_call`, `tests/test_steps.py::test_the_release_is_its_one_tag` |
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
| The Result is taken by the digest `run` reported, and held to its schema | `tests/test_apply.py::test_a_result_is_taken_by_the_digest_run_reported_and_held_to_its_schema` |
| A Result is held to the Decision that admitted its Run | `tests/test_apply.py::test_what_a_result_is_held_to_is_the_decision_that_admitted_its_run` |
| Nothing is minted for a refused Result, and the token is revoked whatever happens | `tests/test_apply.py::test_nothing_is_minted_for_a_refused_result_and_the_token_is_revoked_whatever_happens` |
| The approving act sends one write, the approval of the commit it read, and claims only what it reads back | `tests/test_approve.py::test_the_act_sends_one_write_and_it_is_the_approval` |
| It approves only through the approver's token, for a Decision that issued the approval, what the Kernel still wants | `tests/test_approve.py::test_the_act_approves_only_what_the_kernel_asked_again_still_wants` |
| The reader reads the Task's inputs, held to the Decision, and revokes its token before the model's step | `tests/test_steps.py::test_the_reader_writes_the_tasks_inputs`, `tests/test_steps.py::test_the_reader_fails_closed` |
| A Run whose own Release is not its pass's, or cannot be named, builds no Task | `tests/test_steps.py::test_a_run_on_another_release_than_its_pass_builds_no_task`, `tests/test_steps.py::test_a_run_whose_own_release_cannot_be_named_builds_no_task` |
| A step writes new files of its own and prints a code; `verify` takes the Result by its digest, checks `not_run` | `tests/test_steps.py::test_a_steps_files_are_new_and_its_own`, `tests/test_steps.py::test_verify_takes_the_results_digest` |
| `apply` waits for `run` and `verify`, and reads the item again with reads alone | `tests/test_steps.py::test_apply_waits_for_its_jobs`, `tests/test_steps.py::test_apply_reads_with_reads`, `tests/test_steps.py::test_the_item_is_read_again` |
| The last step leaves the Run's outcome; the approver reads and writes held to its item | `tests/test_steps.py::test_the_last_step_leaves_the_outcome`, `tests/test_steps.py::test_the_approver_holds_to_its_item` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
