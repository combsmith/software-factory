"""The mutants of `schemas/config.schema.json`: tools/mutants.py runs them."""

from tools.mutants_of.common import S3_REPLAY

TARGETS = ("schemas/config.schema.json",)
MUTANTS = [
    # Issues 963 and 965, the reader audits of #918 and #912: each issue's read dated by its own answer, the issues'
    # configuration left as written and its Apps named plain, and every account held to the names an App's id holds.
    ("factory:triage's App may be named with its suffix", 'schemas/config.schema.json',
     '"minLength": 1,\n              "pattern": "^[a-z0-9][a-z0-9-]*$"\n            },\n            "factory:ready"',
     '"minLength": 1\n            },\n            "factory:ready"', S3_REPLAY),
    ("factory:ready's App may be named with its suffix", 'schemas/config.schema.json',
     '"minLength": 1,\n              "pattern": "^[a-z0-9][a-z0-9-]*$"\n            }\n          }\n        },\n        "intents"',
     '"minLength": 1\n            }\n          }\n        },\n        "intents"', S3_REPLAY),
    ("judge-readiness's App may be named with its suffix", 'schemas/config.schema.json',
     '"minLength": 1,\n                  "pattern": "^[a-z0-9][a-z0-9-]*$"\n                }\n              }\n            },\n            "open-pull-request"',
     '"minLength": 1\n                }\n              }\n            },\n            "open-pull-request"', S3_REPLAY),
    ("investigate-issue's App may be named with its suffix", 'schemas/config.schema.json',
     '"minLength": 1,\n                  "pattern": "^[a-z0-9][a-z0-9-]*$"\n                }\n              }\n            },\n            "judge-readiness"',
     '"minLength": 1\n                }\n              }\n            },\n            "judge-readiness"', S3_REPLAY),
    ("open-pull-request's App may be named with its suffix", 'schemas/config.schema.json',
     '"minLength": 1,\n                  "pattern": "^[a-z0-9][a-z0-9-]*$"\n                }\n              }\n            }\n          }',
     '"minLength": 1\n                }\n              }\n            }\n          }', S3_REPLAY),
]
