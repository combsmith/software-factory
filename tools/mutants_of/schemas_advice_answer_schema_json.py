"""The mutants of `schemas/advice-answer.schema.json`: tools/mutants.py runs them."""

ADVICE_ANSWERED = ("tests.test_advisory.Schemas.test_a_readers_answer_is_one_object_of_findings_and_nothing_beside_them",)

TARGETS = ("schemas/advice-answer.schema.json",)
MUTANTS = [
    # Decision 0224: the second transport, what an advisory Lens's reader is asked through.
    ("a reader's answer may hold any number of findings", 'schemas/advice-answer.schema.json',
     '"maxItems": 100',
     '"maxItems": 1000', ADVICE_ANSWERED),
    ("a reader's title may run over lines", 'schemas/advice-answer.schema.json',
     '"pattern": "^[^\\\\x00-\\\\x1f\\\\x7f-\\\\x9f\\\\u061c\\\\u200b-\\\\u200f\\\\u2028-\\\\u202e\\\\u2066-\\\\u2069\\\\ufeff\\\\u00ad\\\\u180e\\\\u2060-\\\\u2064\\\\ufff9-\\\\ufffb\\\\ud800-\\\\udfff\\\\U000e0000-\\\\U000e007f]{1,200}$"',
     '"minLength": 1', ADVICE_ANSWERED),
    ("a reader's file may be any text", 'schemas/advice-answer.schema.json',
     '"pattern": "^[^\\\\x00-\\\\x1f\\\\x7f-\\\\x9f\\\\u061c\\\\u200b-\\\\u200f\\\\u2028-\\\\u202e\\\\u2066-\\\\u2069\\\\ufeff\\\\u00ad\\\\u180e\\\\u2060-\\\\u2064\\\\ufff9-\\\\ufffb\\\\ud800-\\\\udfff\\\\U000e0000-\\\\U000e007f]{1,1024}$"',
     '"minLength": 1', ADVICE_ANSWERED),
    ("a reader's message may be too long for one text's body", 'schemas/advice-answer.schema.json',
     '"maxLength": 65333',
     '"maxLength": 65535', ADVICE_ANSWERED),
    ("a reader's line may be 0", 'schemas/advice-answer.schema.json',
     '"minimum": 1,',
     '"minimum": 0,', ADVICE_ANSWERED),
    ("a reader's answer may be of any version", 'schemas/advice-answer.schema.json',
     '"const": "advice-answer/1"',
     '"type": "string"', ADVICE_ANSWERED),
    ("a reader's criterion may be any text", 'schemas/advice-answer.schema.json',
     '"pattern": "^PR-[0-9]{1,3}$"',
     '"minLength": 1', ADVICE_ANSWERED),
]
