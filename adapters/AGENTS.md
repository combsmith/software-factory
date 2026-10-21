# adapters/

All of the Factory's I/O. `github.py` is the one transport: every request to GitHub goes through it, and nothing else in
this repo reaches the network. `pull.py` reads the facts of a pull request that its own reads give. A port decides nothing
and hands the Kernel no text: what it cannot read whole it says is short, and the title travels beside the facts.

Not built yet, by the stories that hold their rules: records.py, timeline.py, checks.py, facts.py, acceptance.py, issues.py, settings.py, effects.py.

| Rule | Held by |
|---|---|
| Only `github.py` imports what reaches the network | `tests/test_tools.py::test_only_the_transport_reaches_the_network` |
| It sends HTTPS to GitHub's API alone, by a path from its root | `tests/test_adapters.py::test_a_request_stays_on_githubs_api` |
| It follows no redirect, takes no proxy, bounds every answer, and uses the token its caller gives it | `tests/test_adapters.py::test_the_live_transport_takes_its_token_from_its_caller_and_follows_no_redirect` |
| A test replays a trial's fixture, which answers each recorded request once, in order and with its whole body, and refuses any other | `tests/test_adapters.py::test_a_replay_answers_only_what_the_fixture_holds_and_each_once` |
| A read that is not whole says so in its `complete` flag | `tests/test_adapters.py::test_a_diff_that_disagrees_with_the_counts_is_a_short_read`, `tests/test_adapters.py::test_a_list_github_stops_short_of_the_count_is_never_the_whole` |
| A fact that cannot be read is null or refused, never guessed | `tests/test_adapters.py::test_an_activity_that_has_not_caught_up_with_the_head_names_no_one` |
| A head that moved while it was read is refused | `tests/test_adapters.py::test_a_head_that_moved_while_it_was_read_is_refused` |
| An account is told by its id and its type, a Bot for an App and a User for the Maintainer, as the caller names it; anyone else is `outside` | `tests/test_adapters.py::test_the_class_is_the_account_named_or_outside` |
| The title is handed beside the facts, never in them | `tests/test_adapters.py::test_the_pull_requests_own_facts_and_the_title_beside_them` |
| A rule of a part not built yet waits on the file named above, and the story that builds it re-points its rows | `tests/test_tools.py::test_a_wait_on_a_file_a_built_directory_plans_holds_until_the_file_exists` |
