# 1166. A new record is a short why-log held to a word budget

Status: accepted. 2026-11-22, the Maintainer, on the Solution Architect's design; issue 1165. Extends `docs/decisions/0245-a-new-records-title-is-short-and-names-its-file.md`.

## Decision

From this record on, `tools/check_context.py` holds each new record to a budget. The numbers sit beside its cutover there.

| Part | At most |
|---|---|
| Status | 40 words, not counting words in backticks |
| Decision and Why together | 300 words, or 450 when the Status replaces records |
| Decision tables | 8 rows in all, and 40 words to a cell |
| A Boundary row | 30 words of behaviour, and one mutant named in its Check |

A word is a run between spaces with a letter or a digit in it.

From this record on, a record may also give an issue or a pull request by its number alone, as "issue 1165". A bare number after a hash is still refused, and other pages still give the title.

Limits: the check counts words, not clarity, and trusts what an author puts in backticks in the Status. A row names one mutant, so the rule's other mutants run "first" against their tests and then the whole suite, not "only" against them. A test elsewhere that kills one can hide a wrong name.

## Why

Records grew to a median of about 1,060 words, with sentences of about 34 words. About 65% restated the code and tests, so a record went stale whenever the code moved. Quoting each issue's full title made them longer still. A cap on the whole record was rejected, since it would punish Boundaries, and old records stay as they are, since a record is never edited.

## Boundaries

| Boundary | Check |
|---|---|
| From this record on, a Status is at most 40 words; its label and words in backticks are not counted | `tools/check_context.py`, `tests/test_tools.py::test_a_new_records_status_is_held_to_its_words`, mutant: "a new record's Status may be any length" |
| The Decision and the Why are at most 300 words together, or 450 when the Status replaces records; pipes are no words | `tools/check_context.py`, `tests/test_tools.py::test_a_new_records_decision_and_why_are_held_to_their_words`, mutant: "the Decision and the Why may be any length" |
| The Decision's tables have at most 8 rows in all, and no cell over 40 words | `tools/check_context.py`, `tests/test_tools.py::test_a_new_records_decision_table_is_short`, mutant: "a Decision may have any number of rows" |
| A Boundary row's behaviour is at most 30 words, and its Check names one mutant at most | `tools/check_context.py`, `tests/test_tools.py::test_a_new_records_boundary_rows_are_short_and_name_one_mutant`, mutant: "a Check cell may name two mutants" |
| From this record on, a record may give an issue by its number alone; a bare hash number is refused, and older records and other pages give the title | `tools/check_context.py`, `tests/test_tools.py::test_from_the_cutover_a_record_may_give_an_issue_by_its_number`, mutant: "a record before the cutover may give an issue by its number alone" |
