"""The mutants of `config/feed.json`: tools/mutants.py runs them."""

TARGETS = ("config/feed.json",)
MUTANTS = [
    # Issue 838: a Run that ended on a person's code holds its item, and a person is asked what attempts_exhausted asks.
    ("a person is asked another question of a Run that ended person", "config/feed.json",
     '"reason": "run_needs_person",\n      "question": "allowance_spent",\n      "choices": [\n        "renew_allowance",\n        "close"\n',
     '"reason": "run_needs_person",\n      "question": "allowance_spent",\n      "choices": [\n        "close"\n',
     ("tests.test_decide.Ceilings.test_a_run_that_ended_person_holds_the_item_and_calls_a_person_and_spends_no_attempt",)),
    # Issue 757: a Role's Run that ended environment or never started is counted apart from the Run ceiling.
    ("a person at the bound apart is asked another question", "config/feed.json",
     '"reason": "environment_ceiling",\n      "question": "allowance_spent",\n      "choices": [\n        "renew_allowance",\n        "close"\n',
     '"reason": "environment_ceiling",\n      "question": "allowance_spent",\n      "choices": [\n        "close"\n', ("tests.test_decide.Ceilings.test_a_run_that_spent_no_model_is_counted_apart_from_the_run_ceiling",)),
    # A change to a path only a person decides waits under its own code (issue 746, decision 0207).
    ('the feed asks nothing of a change to a person-only path', 'config/feed.json',
     '    {\n      "reason": "path_needs_person",\n      "question": "a_path_needs_you",\n      "choices": [\n        "approve",\n        "close"\n      ]\n    },\n',
     '',
     ('tests.test_tools.Examples.test_every_reason_that_needs_a_person_says_what_is_asked',)),
    ("the feed asks of a person-only path what it asks of a model Lens's input", 'config/feed.json',
     '      "question": "a_path_needs_you",\n',
     '      "question": "a_lens_input_needs_you",\n',
     ('tests.test_decide.TheFactorysOwnRules.test_a_change_to_a_path_only_a_person_decides_waits_for_a_person',)),
    ('the feed offers a person no approval of a change to a person-only path', 'config/feed.json',
     '      "question": "a_path_needs_you",\n      "choices": [\n        "approve",\n',
     '      "question": "a_path_needs_you",\n      "choices": [\n',
     ('tests.test_decide.TheFactorysOwnRules.test_a_change_to_a_path_only_a_person_decides_waits_for_a_person',)),
]
