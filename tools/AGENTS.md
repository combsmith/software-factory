# tools/

The checks, `verify.py` which runs them all, and `mutants.py` which breaks the Kernel on purpose.
`walk.py` lists this working tree's files, and nothing in another nested inside it, for all of them.
It skips local output, Python's caches and the corpus, only while git's index does not hold it, and
reads the index as a file, so no git is needed. CI checks out the commit afresh, so there all else
is committed; an export, with no `.git`, cannot tell, and skips it all.
`make_corpus.py` records every decision the Kernel makes, under a directory git ignores, to hold
another implementation to this one; the required check does not depend on it. `hooks/` holds the
session hooks `.claude/settings.json` runs; `hooks/shell.py` reads a shell command as words for any of them.

| Rule | Held by |
|---|---|
| A check is `check_<name>.py` with `run(root)` returning a list of sentences, and is listed in `CHECKS` in `verify.py` | `tests/test_tools.py::test_every_check_is_run_by_verify` |
| A check has a test in which it fails, run whole against a planted fault, and finds nothing wrong with this repo | `tests/test_tools.py::test_every_check_has_a_test_in_which_it_fails` |
| A check imports only what `STDLIB` in `check_repo.py` lists; a module not yet used is added there in the same change | `tests/test_tools.py::test_third_party_code_is_caught` |
| The tree is walked or copied only by `walk.py`, which skips another working tree nested in this one | `tests/test_tools.py::test_only_the_walk_walks_the_tree`, `tests/test_tools.py::test_another_working_tree_inside_this_one_is_not_read` |
| No link is committed unless `LINKS` in `check_repo.py` names it; the walk lists a link and never follows it | `tests/test_tools.py::test_a_link_is_refused_wherever_it_is`, `tests/test_tools.py::test_every_link_is_listed_and_none_is_followed` |
| No compiled code and no submodule is committed, in any case of its name: Python loads what no check reads | `tests/test_tools.py::test_compiled_code_is_refused_wherever_it_is`, `tests/test_tools.py::test_a_submodule_is_refused` |
| Local output is skipped only while git's index does not hold it, and refused when it does | `tests/test_tools.py::test_local_output_is_skipped_only_while_git_does_not_hold_it`, `tests/test_tools.py::test_committed_local_output_is_refused` |
| A path git's index holds is refused by its name though the working tree no longer has it | `tests/test_tools.py::test_what_git_holds_is_refused_though_gone_from_disk` |
| An index the walk cannot read is a problem, and skips nothing | `tests/test_tools.py::test_an_index_that_cannot_be_read_is_a_problem_and_skips_nothing` |
| A check fails closed: what it does not understand is a problem, and it allows what is named instead of refusing what is known | `tests/test_tools.py::test_a_rule_is_not_dodged_by_writing_the_workflow_another_way` |
| A workflow rule has a counter-example that breaks it and nothing else | `tests/test_tools.py::test_a_rule_with_no_counter_example_is_caught` |
| `make fast` is `make verify` without the test modules in `SLOW`, and is what runs after each edit | `tests/test_tools.py::test_make_fast_is_verify_without_the_seeded_simulation` |
| A session hook is a module in `hooks/` with a `main()`, wired to its event in `.claude/settings.json` and run as `python3 -I`, so no file where it runs can shadow the standard library | `tests/test_hooks.py::test_every_hook_is_wired_to_its_event` |
| A hook runs make only in the project, or in a worktree the project holds | `tests/test_hooks.py::test_an_edit_outside_the_project_runs_nothing` |
| A hook never hands its own git an option taken from the command, and shows no credential | `tests/test_hooks.py::test_a_push_names_no_option_to_the_hooks_own_git`, `tests/test_hooks.py::test_a_credential_is_never_shown` |
| A hook is fed a violation and a clean case. Most cases call the function its `main()` calls; one goes through the front door | `tests/test_hooks.py` |
| A hook that guards an identity refuses what it cannot read: no git or gh, a command it cannot split, a directory it cannot tell | `tests/test_hooks.py::test_what_the_hook_cannot_read_is_refused` |
| Only a failing test kills a mutant; a run that hangs, crashes or cannot import is an `ERROR` | `tests/test_tools.py::test_only_a_failing_test_kills_a_mutant`, `tests/test_tools.py::test_a_run_that_hangs_is_ended_reported_and_fails_the_check` |
| An entry in `mutants.py` names text that appears once in its file. Change that text, or write the same text on a second line, and the entry goes `STALE`; update it | `mutants.py` |

A check collects every problem and does not stop at the first. Its message says what is wrong and
what to do, in one sentence, because an author will read it with nothing else to go on.
