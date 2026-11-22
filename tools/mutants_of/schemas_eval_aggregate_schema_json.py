"""The mutants of `schemas/eval-aggregate.schema.json`: tools/mutants.py runs them."""

TARGETS = ("schemas/eval-aggregate.schema.json",)
MUTANTS = [
    # Issue 613, the preflight: each dispatch of a gate set asks a few development cases first, and a broken pipeline stops it.
    ('a report may say its cells', 'schemas/eval-aggregate.schema.json',
     '  "properties": {\n    "schema": {\n      "const": "eval-aggregate/1"',
     '  "properties": {\n    "cells": {},\n    "schema": {\n      "const": "eval-aggregate/1"', ('tests.test_evals.EvalJob.test_a_gate_sets_sealed_ledger_says_where_two_of_its_groups_overlap_in_a_few_cases_and_nothing_public_does',)),
    # Issue 612: a dispatch names its set; a gate set's report is of counts alone, its ledger sealed to pinned certificates.
    ("a gate set's report need not name the models that answered", 'schemas/eval-aggregate.schema.json',
     '    "engine",\n    "models",\n', '    "engine",\n',
     ('tests.test_evals.EvalJob.test_the_gate_passes_a_good_aggregate_report_and_refuses_a_bad_one',)),
    # Astra and Kimi on #810: the watch keeps a call that gave no answer as one that did not succeed, the retry's ask holds
    # no part of the answer, the wait is read again at its bound, every attempt's seconds are summed, and the report and
    # the ledger hold the retries to RETRIES and a gate set's report its total.
    ("a gate set's report need not carry its total asked again", 'schemas/eval-aggregate.schema.json',
     '    "ledger",\n    "retried"\n  ],', '    "ledger"\n  ],', ('tests.test_evals.EvalJob.test_a_gate_sets_report_counts_the_cases_asked_again_and_its_ledger_marks_each',)),
]
