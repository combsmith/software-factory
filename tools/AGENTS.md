# tools/

The checks, `verify.py` which runs them all, and `mutants.py` which breaks the Kernel on purpose.
`walk.py` lists this working tree's files, and nothing in another nested inside it, for all of them.
`make_corpus.py` records every decision the Kernel makes, under a directory git ignores, to hold
another implementation to this one; the required check does not depend on it.

| Rule | Held by |
|---|---|
| A check is `check_<name>.py` with `run(root)` returning a list of sentences, and is listed in `CHECKS` in `verify.py` | `tests/test_tools.py::test_every_check_is_run_by_verify` |
| A check has a test in which it fails, run whole against a planted fault, and finds nothing wrong with this repo | `tests/test_tools.py::test_every_check_has_a_test_in_which_it_fails` |
| A check imports only what `STDLIB` in `check_repo.py` lists; a module not yet used is added there in the same change | `tests/test_tools.py::test_third_party_code_is_caught` |
| The tree is walked or copied only by `walk.py`, which skips another working tree nested in this one | `tests/test_tools.py::test_only_the_walk_walks_the_tree`, `tests/test_tools.py::test_another_working_tree_inside_this_one_is_not_read` |
| No link is committed unless `LINKS` in `check_repo.py` names it; the walk lists a link and never follows it | `tests/test_tools.py::test_a_link_is_refused_wherever_it_is`, `tests/test_tools.py::test_every_link_is_listed_and_none_is_followed` |
| A check fails closed: what it does not understand is a problem, and it allows what is named instead of refusing what is known | `tests/test_tools.py::test_a_rule_is_not_dodged_by_writing_the_workflow_another_way` |
| A workflow rule has a counter-example that breaks it and nothing else | `tests/test_tools.py::test_a_rule_with_no_counter_example_is_caught` |
| An entry in `mutants.py` names text that appears once in its file. Change that text, or write the same text on a second line, and the entry goes `STALE`; update it | `mutants.py` |

A check collects every problem and does not stop at the first. Its message says what is wrong and
what to do, in one sentence, because an author will read it with nothing else to go on.
