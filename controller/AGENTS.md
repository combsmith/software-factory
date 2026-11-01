# controller/

The Controller. `pass_.py` is one pass as a function of what it read, the configuration, `now`, the pass records before it and a mint for ids: it builds the context, asks the Kernel about every item through `kernel.decide` and `kernel.issue.decide`, and
returns the pass record, the Runs to dispatch by their run-names, the acts, the view's three files, the alerts and whether a successor starts. It reads no clock, writes nothing and decides nothing itself. `reads.py` holds what it reads to the schemas,
`feed.py` and `health.py` write the view, `writes.py` plans the writes, `configuration.py` reads what a pass is told, `shared.py` the schemas. `__main__.py` is the entry the pass job runs (decision 0060). `reconcile.py` matches writes to Effects.
Not built yet, by the stories that hold their rules: relay.py, backpressure.py, notify.py.

| Rule | Held by |
|---|---|
| The pass asks the Kernel through its entry points alone, each Lifecycle's `decide` and `unnamed_scope`, and imports no clock and nothing that reaches out | `tests/test_controller.py::test_the_pass_asks_the_kernel_through_its_entry_points_alone` |
| The pass record holds what the Kernel was given, and replays every Decision | `tests/test_controller.py::test_the_pass_record_holds_what_the_kernel_was_given_and_replays_it` |
| A Run id is minted for an admission or an approval alone | `tests/test_controller.py::test_only_an_admission_or_an_approval_gets_a_run_id` |
| A Run is dispatched by its run-name; a capacity fault defers model Runs for its window | `tests/test_controller.py::test_the_runs_to_dispatch_are_named_by_their_run_names`, `tests/test_controller.py::test_a_capacity_fault_defers_model_runs_for_its_window` |
| An item whose facts are not facts, or listed twice, is left out, as one alert; any other is decided as without it | `tests/test_controller.py::test_an_item_whose_facts_are_not_facts_is_left_out_and_raises_one_alert` |
| An issue is asked of the issues' Kernel, under its own Lifecycle, and its repo's Pause is read | `tests/test_controller.py::test_an_issue_is_asked_of_the_issues_kernel_with_its_own_lifecycle` |
| A record that cannot validate is refused whole, and nothing is dispatched | `tests/test_controller.py::test_a_record_that_cannot_validate_is_refused_and_nothing_is_dispatched` |
| A Pause on the org or a repo is a Pause; a value but exact `true`, exact `false` or none is unreadable | `tests/test_controller.py::test_a_pause_on_the_org_or_the_repo_is_a_pause_and_any_other_value_is_unreadable` |
| The active Runs and the unidentified are read from the records port's list | `tests/test_controller.py::test_the_count_of_active_runs_and_the_unidentified_are_read_from_the_records` |
| A list of runs read short, not at all or holding what is not a run record admits nothing | `tests/test_controller.py::test_a_list_of_runs_read_short_or_not_at_all_admits_nothing` |
| An automatic pause needs faults since a Run last succeeded, on different items, recently; it defers Runs, never an act | `tests/test_controller.py::test_an_automatic_pause_needs_agreeing_faults_from_runs_on_different_items_in_a_recent_window` |
| `passes_since` restarts only after six hours with no pass | `tests/test_controller.py::test_passes_since_restarts_only_after_a_gap_of_the_second_reading` |
| The first pass after six hours with none raises the not-run alert, and the next clears it | `tests/test_controller.py::test_the_first_pass_after_six_hours_with_none_raises_the_not_run_alert_and_the_next_clears_it` |
| The entry reads through the ports with a token of reads alone, and a token not revoked fails it | `tests/test_controller.py::test_the_entry_reads_through_the_ports_and_hands_the_pass_nothing_else` |
| Each snapshot is read with `config/controller.json`'s accounts, by id, and the run list's wholeness, and kept | `tests/test_controller.py::test_each_snapshot_is_read_with_the_configured_accounts_and_kept` |
| Only the entry reads the clock and the environment | `tests/test_controller.py::test_only_the_entry_reads_the_clock_or_the_environment` |
| What the entry cannot read writes nothing, and it says one code | `tests/test_controller.py::test_what_the_entry_cannot_read_writes_nothing` |
| A pass reads no sooner than three minutes after the last began to read | `tests/test_controller.py::test_a_pass_reads_no_sooner_than_three_minutes_after_the_last_pass_began_to_read` |
| A successor starts only for an act due at the end, not one the pass before made, and never while a Run is unidentified | `tests/test_controller.py::test_a_successor_starts_only_for_an_item_due_at_the_end` |
| `started_by` is read from the run, an account by its type and id; one held as null is no one's | `tests/test_controller.py::test_started_by_is_read_from_the_run_and_an_account_by_its_type_and_id` |
| One cause raises one alert, and the pass record keeps them | `tests/test_controller.py::test_one_cause_raises_one_alert`, `tests/test_controller.py::test_the_pass_record_keeps_its_alerts_for_the_tracking_issue` |
| Who acts next and what is asked come from `config/feed.json` alone | `tests/test_controller.py::test_next_actor_and_the_decision_required_are_read_from_the_feed_table_alone` |
| A view rebuilt from the pass records is the view written pass by pass | `tests/test_controller.py::test_a_view_rebuilt_from_the_records_equals_the_view_written_pass_by_pass` |
| Health shows decision 0011's thresholds, null where a figure was not read | `tests/test_controller.py::test_the_three_thresholds_of_decision_0011_are_computed_and_shown` |
| Health shows the last pass, the chain and what started each pass | `tests/test_controller.py::test_health_carries_the_last_pass_the_chain_and_what_started_the_passes` |
| The writes a pass plans go in their order: the acts no write serves yet, the dispatches in the record's order, the tracking issue, the successor | `tests/test_effects.py::test_the_writes_go_in_their_order` |
| No dispatch is sent unless the Pause, read again before it, is exactly `false` on the org and on each repo acted in | `tests/test_effects.py::test_no_act_or_run_is_sent_unless_the_pause_reads_exactly_not_paused_on_every_scope` |
| One tracking issue, the App's by its account: opened with the Maintainer assigned, edited as its causes change, closed when clear | `tests/test_effects.py::test_one_tracking_issue_is_opened_once_edited_in_place_and_closed_when_clear` |
| Two open tracking issues are written to by no one, and a person's own Pause opens none | `tests/test_effects.py::test_a_second_open_tracking_issue_is_never_written`, `tests/test_effects.py::test_the_persons_own_pause_opens_no_tracking_issue` |
| The effects step mints the Controller's token from its key, with the writes it is granted, from a key alone | `tests/test_steps.py::test_the_controller_mints_from_its_key`, `tests/test_steps.py::test_a_token_is_minted_from_a_key_alone` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
