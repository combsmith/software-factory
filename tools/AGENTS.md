# tools/

The checks, `verify.py` which runs them all, `mutants.py` which breaks the Kernel on purpose, a shard to a job in CI, and `needs_passed.py`, which fails the required check unless every job it needs passed, and `commits_are_the_maintainers.py`, which fails it
unless each commit names the Maintainer and a listed account opened it. `walk.py` lists this working tree's files, and nothing in another nested inside it. It skips local output, Python's caches and the corpus, only while git's index does not hold
it, and reads the index as a file, so no git is needed. CI checks out the commit afresh, so there all else is committed; an export, with no `.git`, cannot tell, and skips it all. `make_corpus.py` records every decision the Kernel makes, under a directory git
ignores, to hold another implementation to this one; the required check does not depend on it. `hooks/` holds the session hooks `.claude/settings.json` runs; `hooks/shell.py` reads a shell command as words for any of them. `eval_result.py` scores one Result
against one held-out case, where the case is, and is no check; `context_eval.sh` runs the context's test at the Maintainer's terminal and `context_eval.py` records a run, and neither is a check.
`rulesets_drift.sh` reads the repo's live rulesets through whoever is logged in to gh and redacts each answer outside the repo,
and `rulesets_drift.py` compares what is left with `config/rulesets.json`; it is run by hand and is no check. `machine_user_drift.sh` and `machine_user_drift.py` do the same for the machine user's role, in `config/machine-user.json`.

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
| `make fast` is `make verify` without the test modules in `SLOW`; `make checks` is the checks alone, what the hooks run | `tests/test_tools.py::test_make_fast_is_verify_without_the_seeded_simulation` |
| A session hook is a module in `hooks/` with a `main()`, wired to its event in `.claude/settings.json` and run as `python3 -I`, so no file where it runs can shadow the standard library | `tests/test_hooks.py::test_every_hook_is_wired_to_its_event` |
| A hook runs make only in the project, or in a worktree the project holds | `tests/test_hooks.py::test_an_edit_outside_the_project_runs_nothing` |
| A hook never hands its own git an option taken from the command, and shows no credential | `tests/test_hooks.py::test_a_push_names_no_option_to_the_hooks_own_git`, `tests/test_hooks.py::test_a_credential_is_never_shown` |
| A hook is fed a violation and a clean case. Most cases call the function its `main()` calls; one goes through the front door | `tests/test_hooks.py` |
| A hook that guards an identity refuses what it cannot read: no git or gh, a command it cannot split, a directory it cannot tell | `tests/test_hooks.py::test_what_the_hook_cannot_read_is_refused` |
| A hook that guards what is the Maintainer's asks about what it cannot read within its budget, and says no word of the command. `onFailure: block` needs v2.1.295 | `tests/test_hooks.py::test_the_brace_bomb_is_answered_ask_within_the_deadline` |
| A protected path is protected however it is written (`..`, a link, any case); git's state is read only in the project | `tests/test_hooks.py::test_a_path_written_another_way_still_asks`, `tests/test_hooks.py::test_git_state_is_read_only_inside_the_project` |
| A stop lists every protected or reported path changed against origin's main; a write to a remote branch asks | `tests/test_hooks.py::test_an_edit_made_through_eval_is_listed`, `tests/test_hooks.py::test_a_write_to_the_base_the_stop_compares_with_asks` |
| A test kills a mutant only failing on it, again alone, and passing alone in an unbroken copy; else `FLAKY`, or `ERROR` on a hang: both fail a run | `tests/test_tools.py::test_a_failure_that_is_not_the_mutants_twice_is_flaky_and_fails_the_check` |
| A `mutants.py` entry names text found once in its file (else `STALE`; update it) and tests that kill it, each existing, none in `WHOLE_TOO_LONG` nor its module | `mutants.py`, `tests/test_tools.py::test_every_mutant_names_a_test_that_exists` |
| After the named tests, all of `tests/` runs in dealt parts; `mutants PATH...` breaks at most 40, two at once | `tests/test_tools.py::test_the_whole_suite_runs_in_dealt_parts_each_held_to_the_limit`, `tests/test_tools.py::test_a_filtered_run_is_capped` |

A check collects every problem and does not stop at the first. Its message says what is wrong and what to do, in one sentence, because an author will read it with nothing else to go on.

What the hooks decide without reading is `docs/decisions/0017-the-session-hooks-read-every-commit-a-push-sends.md`, and what
the identity hook reads of git's configuration is `docs/decisions/0024-the-identity-hook-reads-where-a-push-goes-from-gits-configuration-and-refuses-a-git-the-command-may-redefine.md`.
