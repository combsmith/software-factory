"""The mutants of `schemas/facts.schema.json`: tools/mutants.py runs them."""

TARGETS = ("schemas/facts.schema.json",)
MUTANTS = [
    # Issue 526: the facts port reads the description's edits, and an absent edit time is unread, never none (0140).
    ("the edit time is not required", 'schemas/facts.schema.json', '    "last_reopened_at",\n    "description_edited_at",\n',
     '    "last_reopened_at",\n', ("tests.test_evals.TheSet.test_a_case_dropped_under_evals_in_any_file_is_caught",)),
    # Issue 681, trials/P-65.json: each check is given its workflow run's id and its suite's conclusion, both always
    # written where GitHub gives them, refused in any form but their own, and left out only where an answer leaves them out.
    ("a check's run id of 1 is refused", 'schemas/facts.schema.json',
     '            "type": ["integer", "null"],\n            "minimum": 1\n          },\n          "suite_conclusion"',
     '            "type": ["integer", "null"],\n            "minimum": 2\n          },\n          "suite_conclusion"', ('tests.test_adapters.Checks.test_each_check_is_given_its_runs_id_and_its_suites_conclusion',)),
    ("a check's run id may be any number", 'schemas/facts.schema.json',
     '            "type": ["integer", "null"],\n            "minimum": 1\n          },\n          "suite_conclusion"',
     '            "type": ["number", "null"],\n            "minimum": 1\n          },\n          "suite_conclusion"', ('tests.test_adapters.Checks.test_each_check_is_given_its_runs_id_and_its_suites_conclusion',)),
    ("a suite's conclusion may be a number", 'schemas/facts.schema.json',
     '            "type": ["string", "null"],\n            "pattern": "^[a-z_]+$"\n          }\n        }\n      }\n    },\n    "queue"',
     '            "type": ["string", "integer", "null"],\n            "pattern": "^[a-z_]+$"\n          }\n        }\n      }\n    },\n    "queue"', ('tests.test_adapters.Checks.test_each_check_is_given_its_runs_id_and_its_suites_conclusion',)),
    ("a check's run id may be 0", 'schemas/facts.schema.json',
     '            "type": ["integer", "null"],\n            "minimum": 1\n          },\n          "suite_conclusion"',
     '            "type": ["integer", "null"]\n          },\n          "suite_conclusion"', ('tests.test_adapters.Checks.test_each_check_is_given_its_runs_id_and_its_suites_conclusion',)),
    ("a suite's conclusion may be any text", 'schemas/facts.schema.json',
     '            "type": ["string", "null"],\n            "pattern": "^[a-z_]+$"\n          }\n        }\n      }\n    },\n    "queue"',
     '            "type": ["string", "null"]\n          }\n        }\n      }\n    },\n    "queue"', ('tests.test_adapters.Checks.test_each_check_is_given_its_runs_id_and_its_suites_conclusion',)),
    # Issue 823: the facts name the issue the Factory opened a pull request for, a fact the schema does not require.
    ("the schema requires the issue a pull request was opened for", "schemas/facts.schema.json",
     '    "acceptance",\n    "complete",\n', '    "acceptance",\n    "opened_for",\n    "complete",\n', ("tests.test_tools.Examples.test_the_issue_a_pull_request_was_opened_for_is_a_number_from_1_or_null_or_left_out",)),
    ("the schema takes issue 0 as the issue a pull request was opened for", "schemas/facts.schema.json",
     '        "null"\n      ],\n      "minimum": 1\n    },\n    "issue_stands": {\n',
     '        "null"\n      ],\n      "minimum": 0\n    },\n    "issue_stands": {\n', ("tests.test_tools.Examples.test_the_issue_a_pull_request_was_opened_for_is_a_number_from_1_or_null_or_left_out",)),
    # Issue 833: a thread a later review of its Lens superseded is said dropped.
    ('a thread may be said dropped in any word', 'schemas/facts.schema.json',
     'a security Finding\'s stays open",\n            "type": "boolean"\n', 'a security Finding\'s stays open"\n', ('tests.test_adapters.Recorded.test_a_thread_a_later_review_of_its_lens_no_longer_records_is_said_dropped',)),
]
