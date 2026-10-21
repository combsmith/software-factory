# controller/

The Controller. `pass_.py` is one pass as a function of what it read, the configuration, `now`, the pass records before
it and a mint for ids: it builds the context, asks the Kernel about every item through `kernel.decide` and
`kernel.issue.decide`, and returns the pass record, the Runs to dispatch by their run-names, the acts, the view's
three files, the alerts and whether a successor starts. It reads no clock, writes nothing and decides nothing itself.
The writes are the effects port's, and the workflows run it.

Not built yet, by the stories that hold their rules: reconcile.py, relay.py, backpressure.py.

| Rule | Held by |
|---|---|
| The pass asks the Kernel through its two entry points alone, and imports no clock and nothing that reaches out | `tests/test_controller.py::test_the_pass_asks_the_kernel_through_its_two_entry_points_alone` |
| The pass record holds what the Kernel was given, and replays every Decision | `tests/test_controller.py::test_the_pass_record_holds_what_the_kernel_was_given_and_replays_it` |
| A Run id is minted for an admission or an approval alone | `tests/test_controller.py::test_only_an_admission_or_an_approval_gets_a_run_id` |
| Each Run is dispatched by its run-name | `tests/test_controller.py::test_the_runs_to_dispatch_are_named_by_their_run_names` |
| What cannot validate is refused whole, and nothing is dispatched | `tests/test_controller.py::test_a_record_that_cannot_validate_is_refused_and_nothing_is_dispatched` |
| A Pause on the org or a repo is a Pause; a value but exact `true`, exact `false` or none is unreadable | `tests/test_controller.py::test_a_pause_on_the_org_or_the_repo_is_a_pause_and_any_other_value_is_unreadable` |
| The active Runs and the unidentified are read from the records port's list | `tests/test_controller.py::test_the_count_of_active_runs_and_the_unidentified_are_read_from_the_records` |
| A list of runs read short or not at all admits nothing | `tests/test_controller.py::test_a_list_of_runs_read_short_or_not_at_all_admits_nothing` |
| A capacity fault defers model Runs for its window | `tests/test_controller.py::test_a_capacity_fault_defers_model_runs_for_its_window` |
| An automatic pause needs environment faults since a Run last succeeded, on different items, recently | `tests/test_controller.py::test_an_automatic_pause_needs_agreeing_faults_from_runs_on_different_items_in_a_recent_window` |
| `passes_since` restarts only after six hours with no pass | `tests/test_controller.py::test_passes_since_restarts_only_after_a_gap_of_the_second_reading` |
| The pass after six hours with none clears the not-run alert | `tests/test_controller.py::test_a_pass_after_six_hours_with_none_clears_the_not_run_alert_once` |
| A pass reads no sooner than three minutes after the last began to read | `tests/test_controller.py::test_a_pass_reads_no_sooner_than_three_minutes_after_the_last_pass_began_to_read` |
| A successor starts only for an item due at the end, and never while a Run is unidentified | `tests/test_controller.py::test_a_successor_starts_only_for_an_item_due_at_the_end` |
| `started_by` is read from the run, an account by its type and id; one held as null is no one's | `tests/test_controller.py::test_started_by_is_read_from_the_run_and_an_account_by_its_type_and_id` |
| One cause raises one alert | `tests/test_controller.py::test_one_cause_raises_one_alert` |
| Who acts next and what is asked come from `config/feed.json` alone | `tests/test_controller.py::test_next_actor_and_the_decision_required_are_read_from_the_feed_table_alone` |
| A view rebuilt from the pass records is the view written pass by pass | `tests/test_controller.py::test_a_view_rebuilt_from_the_records_equals_the_view_written_pass_by_pass` |
| Health shows decision 0011's thresholds, null where a figure was not read | `tests/test_controller.py::test_the_three_thresholds_of_decision_0011_are_computed_and_shown` |
| Health shows the last pass, the chain and what started each pass | `tests/test_controller.py::test_health_carries_the_last_pass_the_chain_and_what_started_the_passes` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
