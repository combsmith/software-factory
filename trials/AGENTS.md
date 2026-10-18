# trials/

What GitHub was seen to do. Each file is the fixture of one platform trial from section 6 of the
design: what was sent to GitHub in the canary repo, combsmith/software-factory-canary, and what
came back, with every credential removed. The fake GitHub in `sim/` is held to these
(`sim/grounding.py`). How a trial is run is the skill `.claude/skills/run-a-platform-trial/SKILL.md`.
`python3 -m tools.check_trials` checks this folder alone, before a fixture is added to git.

| Rule | Held by |
|---|---|
| A fixture is `<trial>.json` or `<trial>.<what>.json`, validates against `schemas/trial.schema.json`, and records the trial it is named for. Nothing else is kept here | `tests/test_tools.py::test_a_fixture_that_is_misnamed_or_invalid_is_caught` |
| The trial ran in the canary repo | `examples/invalid/trial.run-outside-the-canary.json` |
| No credential: no field named for one at any depth, no string shaped like one, plainly or in base64. Delete it and list where in `removed` | `tests/test_tools.py::test_a_credential_in_a_fixture_is_caught` |
| A header is kept only if `HEADERS` in `tools/check_trials.py` names it | `tests/test_tools.py::test_a_header_a_fixture_may_not_keep_is_caught` |
| The examples of a fixture, counter-examples too, and this file hold no credential either | `tests/test_tools.py::test_every_example_of_a_fixture_and_the_folder_notes_are_scanned` |
| A raw capture is redacted by `tools/redact_trial.py`, outside the repo, before it is read; what comes out passes the rules above | `tests/test_tools.py::test_a_raw_capture_comes_out_with_no_credential` |
| Nothing reads the canary at run time: only a document, a fixture, its example and schema, and the Apps' installs in `config/apps.json` name it. A fixture arrives by pull request | `tests/test_tools.py::test_code_that_reads_the_canary_is_caught` |
| A fixture keeps GitHub's words as said, so it alone may name a model or the proof of concept's private repo | `tests/test_tools.py::test_only_a_fixture_may_name_a_model_or_the_proof_of_concept` |
| A rule of the fake grounded here names a valid fixture of a trial that asks it | `tests/test_tools.py::test_a_fixture_named_for_a_rule_must_exist_and_validate` |
| A trial of a vendor's CLI, as P-13, records `repo` null and asks as `subscription`, never named by its address (decision 0034) | `examples/trial.a-vendors-cli.json`, `examples/invalid/trial.a-subscription-named-by-its-address.json` |
