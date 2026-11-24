"""The mutants of `schemas/eval-report.schema.json`: tools/mutants.py runs them."""

from tools.mutants_of.common import ALSO_AT_JOB, SURPLUS_JOB

TARGETS = ("schemas/eval-report.schema.json",)
MUTANTS = [
    # Decision 0105: the facts the set predates are filled where it is read, in the job alone, and told apart by a code.
    ('a diff over the bound is not a code of the report', 'schemas/eval-report.schema.json',
     '                "diff_not_whole",\n',
     '', ("tests.test_evals.EvalJob.test_a_diff_over_the_bound_says_so_and_asks_nothing",)),
    # Decisions 0120 and 0150: the gate's bar of each kind, what closes it whatever the bar, and what no longer does.
    ("a report need not say of its blocking cases", 'schemas/eval-report.schema.json', '    "kinds_pass",\n    "blocking_pass"\n', '    "kinds_pass"\n', ("tests.test_release_step.Candidate.test_the_eval_gate_is_closed_by_anything_not_read_whole_or_not_passed",)),
    ("the blocking word may be a count", 'schemas/eval-report.schema.json', '"type": ["boolean", "null"]\n', '"type": ["boolean", "integer", "null"]\n', ("tests.test_release_step.Candidate.test_the_eval_gate_is_closed_by_anything_not_read_whole_or_not_passed",)),
    ("a report need not say of its kinds", 'schemas/eval-report.schema.json',
     '    "split_ok",\n    "kinds_pass",\n',
     '    "split_ok",\n', ("tests.test_release_step.Candidate.test_the_eval_gate_is_closed_by_anything_not_read_whole_or_not_passed",)),
    ("a report may name no kind", 'schemas/eval-report.schema.json', '      "required": ["finding", "met"],\n', '', ("tests.test_release_step.Candidate.test_the_eval_gate_is_closed_by_anything_not_read_whole_or_not_passed",)),
    ("a word for met may be a count", 'schemas/eval-report.schema.json', '"met": { "type": "boolean" }', '"met": { "type": ["boolean", "integer"] }', ("tests.test_release_step.Candidate.test_the_eval_gate_is_closed_by_anything_not_read_whole_or_not_passed",)),
    ("a word for finding may be a count", 'schemas/eval-report.schema.json', '"finding": { "type": "boolean" }', '"finding": { "type": ["boolean", "integer"] }', ("tests.test_release_step.Candidate.test_the_eval_gate_is_closed_by_anything_not_read_whole_or_not_passed",)),
    # Decision 0143: a fault may rightly be placed at more than one place, and a case may name each.
    ("the report's mark may be false", 'schemas/eval-report.schema.json',
     '            "type": "boolean",\n            "const": true\n          },\n          "cause": {', '            "type": "boolean"\n          },\n          "cause": {', ALSO_AT_JOB),
    ("the report's mark may be one", 'schemas/eval-report.schema.json', '            "type": "boolean",\n            "const": true\n', '            "const": true\n', ALSO_AT_JOB),
    ("a code of where it went is no code of the report", 'schemas/eval-report.schema.json',
     '"finding_uncited",\n', '"finding_uncitedd",\n', ("tests.test_evals.EvalJob.test_every_code_the_scorer_gives_is_one_the_report_may_carry",)),
    # Issue 610: one Finding at the place, and one gating Finding away from every place, and the report counts them.
    ("the report holds no count", 'schemas/eval-report.schema.json', '          "surplus_gating": {\n', '          "surplus_gating_count": {\n', SURPLUS_JOB),
    ("the report's count may be none", 'schemas/eval-report.schema.json',
     '            "minimum": 1\n          },\n          "retried"',
     '            "minimum": 0\n          },\n          "retried"', SURPLUS_JOB),
    ("the report holds no code for two Findings at the place", 'schemas/eval-report.schema.json',
     '                "surplus_at_place",\n', '', ('tests.test_evals.EvalJob.test_the_gate_holds_each_kinds_bar_and_a_fault_still_closes_it',)),
    ("the report holds no code for gating Findings elsewhere", 'schemas/eval-report.schema.json',
     '                "surplus_gating_elsewhere",\n', '', SURPLUS_JOB),
    # Issue 574: the eval refuses a Result that posts a Finding off every hunk, as `apply` does, and the prompt says so.
    ("the report holds no code for a Finding off every hunk", 'schemas/eval-report.schema.json',
     '                "finding_not_in_hunk",\n', '', ('tests.test_evals.EvalJob.test_the_gate_holds_each_kinds_bar_and_a_fault_still_closes_it',)),
    # Decision 0111: the scorer's codes are the report's and the log's.
    ("a code the scorer gives is no code of the report", 'schemas/eval-report.schema.json',
     '"criterion_unknown"\n', '"criterion_missing"\n', ("tests.test_evals.EvalJob.test_every_code_the_scorer_gives_is_one_the_report_may_carry",)),
    ("a case may still say case_failed", 'schemas/eval-report.schema.json',
     '"answer_off_rubric",\n', '"answer_off_rubric",\n                "case_failed",\n', ("tests.test_evals.EvalJob.test_every_code_the_scorer_gives_is_one_the_report_may_carry",)),
    # Issue 365: a set short of a kind fails the run and closes the gate, and no count of a kind is written.
    ("a report's word may be a count", 'schemas/eval-report.schema.json',
     '    "split_ok": {\n      "type": [\n        "boolean",\n',
     '    "split_ok": {\n      "type": [\n        "integer",\n        "boolean",\n', ('tests.test_evals.TheSet.test_a_case_dropped_under_evals_in_any_file_is_caught',)),
    ('a report may carry a field of its own', 'schemas/eval-report.schema.json',
     '  "additionalProperties": false,\n  "required": [\n    "schema",\n    "release",',
     '  "additionalProperties": true,\n  "required": [\n    "schema",\n    "release",', ('tests.test_evals.TheSet.test_a_case_dropped_under_evals_in_any_file_is_caught',)),
    ('a report need not say', 'schemas/eval-report.schema.json',
     '    "passed",\n    "split_ok",\n',
     '    "passed",\n', ('tests.test_release_step.Candidate.test_the_eval_gate_is_closed_by_anything_not_read_whole_or_not_passed',)),
    # Decision 0162: the schema holds the report's identity and each case's usage, as numbers and ids alone.
    ('a report need not name the models that answered', 'schemas/eval-report.schema.json',
     '    "intent",\n    "models",\n',
     '    "intent",\n', ('tests.test_evals.EvalJob.test_a_report_names_the_model_prompt_and_rubric_and_what_each_case_used',)),
    ('a report need not hash its prompt and rubric', 'schemas/eval-report.schema.json',
     '    "prompt_sha256",\n    "rubric_sha256",\n',
     '', ('tests.test_evals.EvalJob.test_a_report_names_the_model_prompt_and_rubric_and_what_each_case_used',)),
    ('a case need not say what it used', 'schemas/eval-report.schema.json',
     '"reasons",\n          "usage"\n',
     '"reasons"\n', ('tests.test_evals.EvalJob.test_a_report_names_the_model_prompt_and_rubric_and_what_each_case_used',)),
    ('a usage need not give its seconds', 'schemas/eval-report.schema.json',
     '"required": ["turns", "cost_usd", "seconds"]',
     '"required": ["turns", "cost_usd"]', ('tests.test_evals.EvalJob.test_a_report_names_the_model_prompt_and_rubric_and_what_each_case_used',)),
    ('a cost may be words', 'schemas/eval-report.schema.json',
     '"cost_usd": { "type": ["number", "null"]',
     '"cost_usd": { "type": ["number", "string", "null"]', ('tests.test_evals.EvalJob.test_a_report_names_the_model_prompt_and_rubric_and_what_each_case_used',)),
    ('turns may be words', 'schemas/eval-report.schema.json',
     '"turns": { "type": ["integer", "null"]',
     '"turns": { "type": ["integer", "string", "null"]', ('tests.test_evals.EvalJob.test_a_report_names_the_model_prompt_and_rubric_and_what_each_case_used',)),
    ("a model's id may be any words", 'schemas/eval-report.schema.json',
     '"items": { "type": "string", "pattern": "^[a-z0-9.-]{1,64}$" }',
     '"items": { "type": "string" }', ('tests.test_evals.EvalJob.test_a_report_names_the_model_prompt_and_rubric_and_what_each_case_used',)),
    ("a prompt's hash may be any words", 'schemas/eval-report.schema.json',
     '    "prompt_sha256": {\n      "description": "The sha256 of the Role\'s prompt, roles/<role>/prompt.md, at the commit, or null where there is none.",\n      "type": ["string", "null"],\n      "pattern": "^[0-9a-f]{64}$"',
     '    "prompt_sha256": {\n      "description": "The sha256 of the Role\'s prompt, roles/<role>/prompt.md, at the commit, or null where there is none.",\n      "type": ["string", "null"]', ('tests.test_evals.EvalJob.test_a_report_names_the_model_prompt_and_rubric_and_what_each_case_used',)),
    # Astra and Kimi on #810: the watch keeps a call that gave no answer as one that did not succeed, the retry's ask holds
    # no part of the answer, the wait is read again at its bound, every attempt's seconds are summed, and the report and
    # the ledger hold the retries to RETRIES and a gate set's report its total.
    ('a case is reported asked again more often than it may be', 'schemas/eval-report.schema.json',
     '            "minimum": 1,\n            "maximum": 2\n', '            "minimum": 1,\n            "maximum": 3\n', ('tests.test_evals.EvalJob.test_a_transient_fault_is_reported_apart_and_a_retried_case_is_marked',)),
]
