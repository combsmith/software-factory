# docs/

What an author reads when a task calls for it. Nothing here is loaded unless it is opened, so the
root `AGENTS.md` points here by task. `prd/`, `architecture/` and `research/` hold the design as it
was written elsewhere: they are read, not edited to fit the rules below, and not held to them.
Build from the sections the design's own section 1.2 calls rules, and never from the review.

| Rule | Held by |
|---|---|
| A path in backticks is a path in this repo and exists; so does a test named after `::`. Name another repo's files in plain words | `tests/test_tools.py::test_a_path_or_a_test_that_does_not_exist_is_caught` |
| Every rule names its check. One whose check cannot exist yet says "waiting on" and a reserved directory in backticks | `tests/test_tools.py::test_a_rule_with_no_check_is_caught`, `tests/test_tools.py::test_a_rule_whose_wait_is_over_is_caught` |
| `standards/`: one page each, at most 120 lines. Each section is an example in a code fence, then the rule, then a line starting "Held by:". No page for review | `tests/test_tools.py::test_a_standard_with_prose_and_no_example_is_caught` |
| `decisions/`: one decision to a file, with sections Decision, Why and Boundaries | `tests/test_tools.py::test_a_decision_with_no_boundary_is_caught` |
| `decisions/`: a record takes the number of the pull request that adds it, one at most; no two share one | `tests/test_tools.py::test_each_record_a_pull_request_adds_is_numbered_by_it`, `tests/test_tools.py::test_no_two_records_share_a_number` |
| `decisions/`: from record 0245 on, a title of at most 72 characters, and the file named by it: lowercased, all but a-z, 0-9, spaces, dashes dropped, a run of spaces one dash | `tests/test_tools.py::test_a_new_records_title_is_short_and_names_its_file` |
| `decisions/`: a record is never edited. A new one replaces it, its Status saying so; the old Status then says "replaced by" and its path, and is fixed. Boundaries only gain rows or change a Check cell | `tools/check_decisions.py` |
| `lessons.md`: a failure that happened, its rule, its check, on lines starting "**Failure.**", "**Rule.**" and "**Check.**" | `tests/test_tools.py::test_a_lesson_with_no_check_is_caught` |
| An issue or pull request is given by its title in quotes, then its number in words | `tests/test_tools.py::test_a_number_without_its_title_is_caught` |
| A secret is named, never written | `tools/check_repo.py` |

A decision record states what is decided now, not how it was reached. Adding a boundary row when a
check for it is written changes nothing decided. `glossary.md` gives each term one meaning;
`context-engineering.md` says why these files are shaped as they are, with sources; `development.md`
says how a change is made here, from a branch to a merge.
