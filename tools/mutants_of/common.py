"""What more than one file of mutants uses: tools/mutants.py and tools/mutants_of/ read it. It imports nothing."""

ADVICE_RESULT = ("tests.test_advisory.Schemas.test_an_advisory_result_holds_codes_and_findings_that_are_advisory_annotations",)
RESULT_PORT = ("tests.test_adapters.Contract.test_a_results_check_is_read_as_any_check_and_a_created_one_is_foreign_to_its_reporter",)
WIRE_PASSES = ("tests.test_adapters.EffectsRecorded.test_each_pass_in_the_window_is_read_once_and_what_cannot_be_read_is_read_again",)
WIRE_AGAIN = ("tests.test_adapters.EffectsRecorded.test_a_pass_that_did_not_succeed_and_lists_none_is_read_after_a_second_look",)
WIRE_RUNS_AGAIN = ("tests.test_adapters.EffectsRecorded.test_a_run_that_did_not_succeed_and_lists_none_is_read_after_a_second_look",)
WIRE_ENTRY = ("tests.test_controller.Entry.test_the_entry_gathers_what_reconciliation_reads",)
INDEX_ONE = ("tests.test_adapters.Diff.test_index_ids_of_any_length_are_one_content",)
# S3, the issues pass: the tests that kill its mutants.
S3_PORT = ("tests.test_adapters.Issues.test_a_factory_app_is_named_by_the_id_the_configuration_holds_and_a_person_never_is",)
S3_REPLAY = ("tests.test_controller.Record.test_an_issue_decision_replays_through_the_issues_kernel_configuration",)
S3_LINKED = ("tests.test_controller.Entry.test_an_issue_whose_linked_pull_requests_were_not_read_defers_through_the_entry",)
S3_RIVAL = ("tests.test_adapters.Linked.test_a_merge_beside_a_rival_keyword_link_is_read_by_the_spans_the_pass_records_give",)
S3_ENTRY = ("tests.test_controller.Entry.test_the_open_issues_are_listed_from_served_from_and_each_read_as_a_pull_request_is",)
S3_NAMED = ("tests.test_controller.Issues.test_an_app_is_named_by_the_id_the_configuration_holds_so_its_label_and_comment_count",)
F901_ROLE = ("tests.test_adapters.Issues.test_a_role_apps_comment_is_its_roles_and_no_act_of_its_is_counted_on_an_issue_or_a_pull_request",)
F901_NAMES = ("tests.test_controller.Entry.test_a_queues_or_a_lenss_name_declared_as_an_issues_app_refuses_the_issues_alone_and_the_pull_requests_are_decided",)
F849_PORT = ("tests.test_adapters.Issues.test_an_issues_timeline_is_read_to_its_bound_and_past_it_is_bounded_and_not_whole",)
F849_LINKED = ("tests.test_adapters.Linked.test_a_linked_pull_requests_own_facts_are_read_as_a_pull_requests_are",)
F849_SPANS = ("tests.test_adapters.KeywordSpans.test_a_record_that_left_the_issue_out_by_its_budget_is_passed_over_for_it_alone",)
F849_SAID = F849_SPANS + ("tests.test_adapters.Linked.test_a_chain_of_spans_the_records_broke_while_something_names_the_issue_is_said",)
ALSO_AT = ("tests.test_evals.Scoring.test_a_finding_at_any_place_the_case_gives_is_at_the_place",)
ALSO_AT_JOB = ("tests.test_evals.EvalJob.test_a_pass_at_an_alternate_place_alone_is_marked_in_the_report_and_counted",)
APART = ("tests.test_evals.EvalJob.test_each_head_is_unpacked_apart_from_the_cases",)
NO_ANSWER = ("tests.test_evals.EvalJob.test_a_run_is_given_no_part_of_its_cases_answer_and_its_head_no_history",)
SURPLUS_JOB = ("tests.test_evals.EvalJob.test_the_report_counts_each_cases_gating_findings_away_from_the_place",)
NEXT_CUT_FIXTURE = ("tests.test_release.Fixture.test_the_next_cut_moved_next_on",)
POINT_FIRST = ("tests.test_release.Points.test_the_first_decision_point_is_of_slice_1s_event_and_its_count_is_read_against_the_designs_figure",)
POINT_EACH = ("tests.test_release.Points.test_each_counter_example_is_wrong_in_its_one_way",)
PERSON_KERNEL = ("tests.test_decide.TheFactorysOwnRules.test_a_change_to_a_path_only_a_person_decides_waits_for_a_person",)
NAMED_MUTANTS = ("tests.test_tools.Decisions.test_a_new_or_changed_row_names_the_mutant_its_test_kills",)
MAIN_ROWS = ("tests.test_tools.Decisions.test_a_row_main_holds_names_no_mutant_until_its_check_changes",)
OPENER_TESTS = ("tests.test_tools.Workflows.test_a_pull_request_is_opened_from_this_repo_by_an_account_the_configuration_allows",)
NEEDED = ("tests.test_tools.Workflows.test_each_step_limit_holds_what_its_step_needs",)
P50_TESTS = "tests.test_tools.LinuxSandboxTrial."
P59_TESTS = "tests.test_tools.ReadConfinementTrial."
HOOK_TESTS = "tests.test_hooks.ProtectedPaths."
SESSION_TESTS = (HOOK_TESTS + "test_a_command_that_runs_claude_code_with_no_one_asked_asks",
                 HOOK_TESTS + "test_claude_code_given_what_the_hook_cannot_read_asks")
IDENTITY_TESTS = "tests.test_hooks.Identity."
PROTECTED_NEST = "tests.test_hooks.MergesAndSettings.test_a_substitution_in_double_quotes_has_quotes_of_its_own_at_every_level"
PROTECTED_NESTED_IN_ONE = ("tests.test_hooks.MergesAndSettings."
                           "test_a_double_quoted_substitution_in_a_double_quoted_one_hides_no_command_after_it")
REDEFINE_TESTS = (IDENTITY_TESTS + "test_a_git_the_command_may_redefine_is_refused",)
ALIAS_TESTS = (IDENTITY_TESTS + "test_an_alias_whose_value_runs_git_or_gh_is_refused",)
BEGAN = ("tests.test_adapters.Records.test_a_run_began_when_a_job_of_it_did",)
SENTENCE_TESTS = ("tests.test_tools.Examples.test_every_reason_a_pull_request_carries_has_one_plain_sentence",)
LOOP_TESTS = (IDENTITY_TESTS + "test_a_loops_word_list_is_data_and_its_body_is_read",)
PATTERN_TESTS = (IDENTITY_TESTS + "test_a_substitution_in_a_case_pattern_runs_where_the_pattern_stands",)
ALIASED_TESTS = (IDENTITY_TESTS + "test_an_alias_for_a_feeder_a_shell_source_or_eval_is_read_as_its_value",)
QUOTED_TESTS = (IDENTITY_TESTS + "test_a_substitution_in_double_quotes_is_read_with_quotes_of_its_own",)
COMMENT_TESTS = (IDENTITY_TESTS + "test_a_comment_or_a_parameter_expansion_in_a_substitution_does_not_end_it",)
SPLIT_TESTS = (IDENTITY_TESTS + "test_a_command_that_cannot_be_split_is_refused_whatever_it_names",)
FOUR_MORE_TESTS = (IDENTITY_TESTS + "test_four_more_ways_to_redefine_git_are_refused",)
# Decision 0040: where the shell may stand, and a program the hook does not read.
PLACED_TESTS = (IDENTITY_TESTS + "test_a_cd_the_hook_cannot_place_exactly_loses_the_directory",)
OWN_CD_TESTS = (IDENTITY_TESTS + "test_a_subshells_cd_is_its_own",)
EXPANSION_TESTS = (IDENTITY_TESTS + "test_a_variable_in_an_expansion_the_hook_does_not_read_may_be_anything",)
BACKSLASH_TESTS = (IDENTITY_TESTS + "test_a_backslash_in_double_quotes_is_read_as_the_shell_reads_it",)
RUNNER = "tests.test_tools.Mutants."
# Each of the SA's ruling of 2026-11-26 on the raw answers' directory, as (name, old, new), for every token script
# (tools_trial_p12_status_sh.py and tools_trial_p52_pause_sh.py both read it).
KEEP_1215 = (
    ("%s keeps its raw answers without --keep-raw", '    [ -n "$keep" ] || rm -rf', '    [ -n "1" ] || rm -rf'),
    ("%s deletes its raw answers though --keep-raw asked", "{ keep=1; shift; }", "{ shift; }"),
    ("%s deletes each raw answer though --keep-raw asked", 'drop() { [ -n "$keep" ] || rm -f -- "$@"; }', 'drop() { rm -f -- "$@"; }'),
    ("%s does not say where it kept its raw answers", '"$scratch" >&2\n}\n', '"$scratch" >/dev/null\n}\n'),
    ("%s makes its raw answers' directory for others to read", 'scratch=$(cd "$made" && pwd -P)\n', 'chmod 755 "$made"\nscratch=$(cd "$made" && pwd -P)\n'),
    ("%s keeps a scratch directory inside the repo", "    exit 2 ;;\nesac\n# The exit trap", "    ;;\nesac\n# The exit trap"),
    ("%s keeps a redacted raw answer to the end", '2> "$out/redacted-$n"\n    drop "$scratch/raw-$n"\n', '2> "$out/redacted-$n"\n'),
)
# Issue 1288: the line each token script unsets the proxy and certificate authority variables curl reads with.
UNPROXIED = "unset http_proxy HTTP_PROXY https_proxy HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY CURL_CA_BUNDLE SSL_CERT_FILE SSL_CERT_DIR\n"
# common.py holds no mutants. Its MUTANTS is empty so that a loader that read it as a file of them would still import,
# and the loader's test would tell the mistake as a failure, not an import's AttributeError (#1153's merge group).
MUTANTS = ()
