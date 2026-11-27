"""The mutants of `schemas/harness.schema.json`: tools/mutants.py runs them."""

TARGETS = ("schemas/harness.schema.json",)
MUTANTS = [
    # Decision 0224: a reader's model and deployment are pinned under readers in the pin's file.
    ("a reader may run past the step's limit", 'schemas/harness.schema.json',
     '"maximum": 1200',
     '"maximum": 12000', ('tests.test_tools.Repo.test_a_reader_pins_its_model_and_its_deployment_at_their_own_paths_and_nowhere_else',)),
    ("a reader's host may be any host", 'schemas/harness.schema.json',
     '"pattern": "^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\\\\.(openai\\\\.azure\\\\.com|services\\\\.ai\\\\.azure\\\\.com|cognitiveservices\\\\.azure\\\\.com)$"',
     '"minLength": 1', ('tests.test_tools.Repo.test_a_reader_pins_its_model_and_its_deployment_at_their_own_paths_and_nowhere_else',)),
    ("the day's ceiling may be nought", 'schemas/harness.schema.json',
     '"advisory_ceiling_usd_per_day": {\n      "type": "number",\n      "minimum": 0.01,',
     '"advisory_ceiling_usd_per_day": {\n      "type": "number",\n      "minimum": 0,', ('tests.test_tools.Repo.test_a_reader_is_an_advisory_lens_and_the_days_ceiling_has_no_default',)),
    # Decision 0224: the worst case one read is counted at, held by tools/check_examples.py (worded in 0243).
    ('the worst case one read is counted at may be nought', 'schemas/harness.schema.json',
     '"advisory_worst_case_usd": {\n      "type": "number",\n      "minimum": 0.01,',
     '"advisory_worst_case_usd": {\n      "type": "number",\n      "minimum": 0,', ('tests.test_tools.Repo.test_a_reader_is_an_advisory_lens_and_the_days_ceiling_has_no_default',)),
    ("a reader's model is held to lower case", 'schemas/harness.schema.json',
     '"pattern": "^[A-Za-z0-9][A-Za-z0-9.-]{0,127}$"',
     '"pattern": "^[a-z0-9][a-z0-9.-]{0,127}$"', ('tests.test_tools.Repo.test_a_reader_pins_its_model_and_its_deployment_at_their_own_paths_and_nowhere_else',)),
]
