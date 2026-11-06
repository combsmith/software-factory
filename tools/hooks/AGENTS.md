# tools/hooks/

The session hooks `.claude/settings.json` runs, and `make.py`, which runs a make target for them. The rules of every
tool, the hooks among them, are in `tools/AGENTS.md`; these are the hooks' own. A hook change is tried live only once it
is on the main checkout's branch: a session runs that copy, wherever it started.

| Rule | Held by |
|---|---|
| Each command in `.claude/settings.json` runs the main checkout's copy of its hook, wherever the session started | `tests/test_hooks.py::test_every_hook_runs_the_main_checkouts_copy_wherever_the_session_started` |
| Where no main checkout's copy is found from the project folder's git common directory, nothing runs, and the person is told in one line | `tests/test_hooks.py::test_every_hook_runs_the_main_checkouts_copy_wherever_the_session_started` |
| `make checks` is not run again, after an edit or at a stop, where it last passed at the same state: each file the walk reads, HEAD and origin's main | `tests/test_hooks.py::test_any_change_the_checks_could_read_runs_them_again` |
| A state that reads differently after the run, or cannot be read, skips nothing | `tests/test_hooks.py::test_only_a_pass_whose_state_held_through_the_run_is_written_down`, `tests/test_hooks.py::test_a_record_or_a_state_that_cannot_be_read_skips_nothing` |
