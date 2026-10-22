# harness/

The Harness: the jobs that carry one Run. `task.py` builds the Task from the Decision that admitted the Run, `engine.py`
runs the vendor's CLI on it and takes the Result from its answer, and `run.py` is the `run` job, which writes the
Result and its digest and nothing else of the model. The model is given no tool, and the CLI no secret but the one
under its own name. Every test drives a stand-in for the CLI: the first live Run is the workflows' and the Release's.
`approve.py` is the approving act, a Run with no Engine: through the machine user's token alone it approves the commit
it read, only if the Kernel asked again still wants it, and says whose fault each failure was (decision 0055). Its
tests drive a stand-in GitHub; its step lands with the approving workflow (issue 196).

Not built yet, by the stories that hold their rules: apply.py, verify.py.

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
| The approving act sends one write, the approval of the commit it read | `tests/test_approve.py::test_the_act_sends_one_write_and_it_is_the_approval` |
| It claims only what it reads back | `tests/test_approve.py::test_the_act_approves_the_commit_it_read_and_claims_only_what_it_reads_back` |
| It approves only through the approver's own token | `tests/test_approve.py::test_only_the_approvers_own_token_approves` |
| It approves only for a Decision that issued the approval | `tests/test_approve.py::test_a_run_no_decision_issued_an_approval_for_finds_none_and_writes_nothing` |
| It approves only what the Kernel, asked again, still wants | `tests/test_approve.py::test_the_act_approves_only_what_the_kernel_asked_again_still_wants` |
| Each of its faults is classed by its status and what is read again, never as `capacity` | `tests/test_approve.py::test_each_fault_of_the_act_is_classed_as_the_design_classes_it` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
