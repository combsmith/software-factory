# tools/

The checks, `verify.py` which runs them all, and `mutants.py` which breaks the Kernel on purpose.
`make_corpus.py` records every decision the Kernel makes, under a directory git ignores, to hold
another implementation to this one; the required check does not depend on it.

| Rule | Held by |
|---|---|
| A check is `check_<name>.py` with `run(root)` returning a list of sentences, and is listed in `CHECKS` in `verify.py` | `tests/test_tools.py::test_every_check_is_run_by_verify` |
| A check has a test in which it fails, against a planted fault | `tests/test_tools.py::test_every_check_has_a_test_in_which_it_fails` |
| A check reaches no network. A standard-library module not yet used is added to `STDLIB` in the same change | `check_repo.py` |
| A check fails closed: what it does not understand is a problem | `tests/test_tools.py::test_rejects_a_schema_it_cannot_enforce` |
| A workflow rule has a counter-example that breaks it and nothing else | `tests/test_tools.py::test_a_rule_with_no_counter_example_is_caught` |
| An entry in `mutants.py` names text that appears once in its file. Change that text, or write the same text on a second line, and the entry goes `STALE`; update it | `mutants.py` |

A check collects every problem and does not stop at the first. Its message says what is wrong and
what to do, in one sentence, because an author will read it with nothing else to go on.
