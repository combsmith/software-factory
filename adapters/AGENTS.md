# adapters/

All of the Factory's I/O. `github.py` is the one transport: every request to GitHub goes through it, and nothing else in
this repo reaches the network. `pull.py` reads the facts of a pull request that its own reads give, `timeline.py` its reviews, labels and who acted,
`checks.py` its checks and its place in the queue, `threads.py` its review threads, `facts.py` the one snapshot of it all,
`records.py` the Factory's own run records, `artifacts.py` a failed Run's outcome from its artifact, `acceptance.py`
whether the issues it closes ask for a contract, and `heldout.py` the held-out home's cases, for the eval job alone. A port decides nothing
and hands the Kernel no text: what it cannot read whole it says is short, and the title travels beside the facts.

Not built yet, by the stories that hold their rules: items.py, contract.py, binding.py, issues.py, settings.py, effects.py, usage.py, texts.py, identity.py.

| Rule | Held by |
|---|---|
| Only `github.py` imports what reaches the network, or names the storage | `tests/test_tools.py::test_only_the_transport_reaches_the_network`, `tests/test_tools.py::test_only_the_transport_names_githubs_artifact_storage` |
| It sends HTTPS to GitHub's API alone, by a path from its root | `tests/test_adapters.py::test_a_request_stays_on_githubs_api` |
| It follows no redirect but an artifact's download, takes no proxy, bounds every answer, and uses the token its caller gives it | `tests/test_adapters.py::test_the_live_transport_takes_its_token_from_its_caller_and_follows_no_redirect` |
| An artifact's download alone follows its redirect, to GitHub's artifact storage alone, over HTTPS | `tests/test_adapters.py::test_only_an_artifacts_download_follows_its_redirect_and_only_to_githubs_storage` |
| No token is sent to the storage, and what it answers is bounded | `tests/test_adapters.py::test_the_live_transport_sends_no_token_to_the_storage_and_bounds_what_it_holds` |
| A failed Run's outcome alone is read, once for each attempt | `tests/test_adapters.py::test_the_outcome_is_read_for_a_run_that_did_not_succeed_and_for_no_other`, `tests/test_adapters.py::test_an_outcome_is_read_once_and_kept_by_its_run_and_attempt` |
| An outcome is bounded and held to `outcome/1` and its Run; what cannot be read is not whole | `tests/test_adapters.py::test_an_outcome_that_cannot_be_read_whole_is_not_whole` |
| A test replays a trial's fixture, which answers each recorded request once, in order and with its whole body, and refuses any other | `tests/test_adapters.py::test_a_replay_answers_only_what_the_fixture_holds_and_each_once` |
| A read that is not whole says so in its `complete` flag | `tests/test_adapters.py::test_a_diff_that_disagrees_with_the_counts_is_a_short_read`, `tests/test_adapters.py::test_a_list_github_stops_short_of_the_count_is_never_the_whole` |
| A fact that cannot be read is null or refused, never guessed | `tests/test_adapters.py::test_an_activity_that_has_not_caught_up_with_the_head_names_no_one` |
| A head that moved while it was read is refused | `tests/test_adapters.py::test_a_head_that_moved_while_it_was_read_is_refused` |
| An account is told by its id and its type, a Bot for an App and a User for the Maintainer, as the caller names it; anyone else is `outside` | `tests/test_adapters.py::test_the_class_is_the_account_named_or_outside` |
| A run counts only as a dispatch of a Role's workflow from this repo's default branch; its name says whose it is | `tests/test_adapters.py::test_only_a_dispatch_of_a_role_workflow_from_the_default_branch_in_this_repo_counts` |
| A counted run not yet named is reported by its id after one more read 5 s later, and every read of runs is uncached | `tests/test_adapters.py::test_a_run_listed_under_its_workflows_name_is_unidentified_after_one_more_read` |
| Write access is a person's alone, read from the collaborator permission, admin, maintain or write, once a login | `tests/test_adapters.py::test_an_actor_is_told_by_its_account_type_and_the_configuration` |
| Each review thread is read with who opened and resolved it, told by account; a person's is `human`, and no comment's text is read | `tests/test_adapters.py::test_each_thread_is_read_with_who_opened_and_resolved_it_and_a_persons_is_human` |
| A thread is a Lens's only when its author is that Lens's own App; only a required model Lens's open thread with no category defers | `tests/test_adapters.py::test_only_a_required_lenss_own_apps_open_thread_defers` |
| Threads are whole only when every one counted was read, once, and no cursor repeats | `tests/test_adapters.py::test_threads_are_read_page_by_page_and_whole_only_when_every_one_was_read_once` |
| A review's dismissal, its dismisser and its state before are read from the timeline; no text of GitHub's is kept | `tests/test_adapters.py::test_reviews_are_read_with_their_commit_content_and_who_dismissed_them` |
| Every check run on the head is given with its exact name, its App and its workflow file, and none dropped | `tests/test_adapters.py::test_every_check_run_on_the_head_is_read_with_its_name_app_and_workflow` |
| The snapshot is refused when the pull request moved while it was read, and is held to `facts/1` | `tests/test_adapters.py::test_a_snapshot_whose_head_moved_while_it_was_read_is_refused` |
| An issue asks for a contract only by an Intent that asks or a person's `factory:contract` label; if none asks, `acceptance` is null and whole | `tests/test_adapters.py::test_an_issue_asks_for_a_contract_only_by_a_persons_label` |
| Closing references read short, of another repo or named twice, are not whole | `tests/test_adapters.py::test_closing_references_are_whole_only_of_this_repo_and_every_one_counted` |
| A pull request to another base than the default is not whole on its contract | `tests/test_adapters.py::test_a_pull_request_to_another_base_than_the_default_is_not_read_whole_on_its_contract` |
| A held-out case is the bytes its manifest hashed, or none and a code; one that could name another file is not asked | `tests/test_adapters.py::test_a_held_out_case_is_its_hashed_bytes`, `tests/test_adapters.py::test_a_held_out_case_not_read_whole_says_why` |
| The title is handed beside the facts, never in them | `tests/test_adapters.py::test_the_pull_requests_own_facts_and_the_title_beside_them` |
| A rule of a part not built yet waits on the file named above, and the story that builds it re-points its rows | `tests/test_tools.py::test_a_wait_on_a_file_a_built_directory_plans_holds_until_the_file_exists` |
