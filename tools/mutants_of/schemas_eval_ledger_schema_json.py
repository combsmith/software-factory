"""The mutants of `schemas/eval-ledger.schema.json`: tools/mutants.py runs them."""

TARGETS = ("schemas/eval-ledger.schema.json",)
MUTANTS = [
    # Issue 141: a Consumer entry's protected paths are in the hooks' syntax, one at least, each once as written, and
    # name its setup and test scripts.
    ('a ledger need hold no preflight', 'schemas/eval-ledger.schema.json',
     '    "cases",\n    "preflight",\n',
     '    "cases",\n', ('tests.test_evals.TheSet.test_a_case_dropped_under_evals_in_any_file_is_caught',)),
    # Issue 613, the preflight: each dispatch of a gate set asks a few development cases first, and a broken pipeline stops it.
    ('a cell need say nothing', 'schemas/eval-ledger.schema.json',
     '        "required": [\n          "kind",\n          "criterion",\n          "natural",\n          "cases",\n          "few"\n        ],\n',
     '        "required": [],\n', ('tests.test_evals.EvalJob.test_a_gate_sets_sealed_ledger_says_where_two_of_its_groups_overlap_in_a_few_cases_and_nothing_public_does',)),
    ("a cell's flag may be a word", 'schemas/eval-ledger.schema.json',
     '            "type": "integer",\n            "enum": [\n              0,\n              1\n            ]\n',
     '            "enum": [\n              0,\n              1\n            ]\n', ('tests.test_evals.EvalJob.test_a_gate_sets_sealed_ledger_says_where_two_of_its_groups_overlap_in_a_few_cases_and_nothing_public_does',)),
    ("a cell's count may be any text", 'schemas/eval-ledger.schema.json',
     '            "pattern": "^[0-9]{1,9}$"\n',
     '            "pattern": "^.*$"\n', ('tests.test_evals.EvalJob.test_a_gate_sets_sealed_ledger_says_where_two_of_its_groups_overlap_in_a_few_cases_and_nothing_public_does',)),
    ('a ledger need not say its cells', 'schemas/eval-ledger.schema.json',
     '    "preflight",\n    "cells"\n  ],',
     '    "preflight"\n  ],', ('tests.test_evals.EvalJob.test_a_gate_sets_sealed_ledger_says_where_two_of_its_groups_overlap_in_a_few_cases_and_nothing_public_does',)),
    # Astra and Kimi on #810: the watch keeps a call that gave no answer as one that did not succeed, the retry's ask holds
    # no part of the answer, the wait is read again at its bound, every attempt's seconds are summed, and the report and
    # the ledger hold the retries to RETRIES and a gate set's report its total.
    ("a ledger's case is asked again more often than it may be", 'schemas/eval-ledger.schema.json',
     '            "maximum": 2\n          },\n          "natural": {', '            "maximum": 3\n          },\n          "natural": {', ('tests.test_evals.EvalJob.test_a_gate_sets_report_counts_the_cases_asked_again_and_its_ledger_marks_each',)),
    ("a ledger's preflight case is asked again more often than it may be", 'schemas/eval-ledger.schema.json',
     '            "maximum": 2\n          },\n          "result": {', '            "maximum": 3\n          },\n          "result": {', ('tests.test_evals.EvalJob.test_a_gate_sets_report_counts_the_cases_asked_again_and_its_ledger_marks_each',)),
]
