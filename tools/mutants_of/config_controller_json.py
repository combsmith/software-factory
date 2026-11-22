"""The mutants of `config/controller.json`: tools/mutants.py runs them."""

TARGETS = ("config/controller.json",)
MUTANTS = [
    # Issue 338: what each Lens recorded, read from its Runs' applied/1; every recorded thread read, opened by that Lens;
    # a Lens thread's category and severity joined from its one Finding the Lens owns.
    ("the reviewer the configuration requires is listed as no Lens", 'config/controller.json',
     '    "lenses": [\n      {\n        "lens": "pr-review",\n        "login": "combsmith-sf-pr-review[bot]",\n        "id": 344166014\n      }\n    ],\n', '    "lenses": [],\n', ('tests.test_adapters.Recorded.test_a_thread_the_required_reviewers_own_app_opened_is_its_lenss_by_the_configured_accounts',)),
    ("the reviewer is listed as a Lens under an account that is not its Role's", 'config/controller.json',
     '    "lenses": [\n      {\n        "lens": "pr-review",\n        "login": "combsmith-sf-pr-review[bot]",\n        "id": 344166014\n      }\n    ],\n', '    "lenses": [\n      {\n        "lens": "pr-review",\n        "login": "combsmith-sf-pr-review[bot]",\n        "id": 344165726\n      }\n    ],\n', ('tests.test_adapters.Recorded.test_a_thread_the_required_reviewers_own_app_opened_is_its_lenss_by_the_configured_accounts',)),
]
