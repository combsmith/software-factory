"""The mutants of `schemas/feed.schema.json`: tools/mutants.py runs them."""

from tools.mutants_of.common import SENTENCE_TESTS

TARGETS = ("schemas/feed.schema.json",)
MUTANTS = [
    # The feed's one plain sentence for each reason a pull request carries, and the one text it holds (decision 1123).
    ("the feed may leave its sentences out", "schemas/feed.schema.json", '    "decision_required",\n    "sentences"\n', '    "decision_required"\n',
     SENTENCE_TESTS),
    ("a sentence of the feed may be 101 characters", "schemas/feed.schema.json", '        "maxLength": 100,\n', '        "maxLength": 101,\n',
     SENTENCE_TESTS),
    ("a sentence may open in lower case", "schemas/feed.schema.json", '"pattern": "^[A-Z][A-Za', '"pattern": "^[A-Za-z][A-Za', SENTENCE_TESTS),
    ("a sentence may hold a second sentence", "schemas/feed.schema.json", ",;:'()-]*[.]$", ",;:'().-]*[.]$", SENTENCE_TESTS),
    ("a sentence may end with no full stop", "schemas/feed.schema.json", ",;:'()-]*[.]$", ",;:'()-]*$", SENTENCE_TESTS),
]
