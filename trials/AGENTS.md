# trials/

What GitHub was seen to do. Each file is the fixture of one platform trial from section 6 of the
design: what was sent to GitHub in the canary repo, combsmith/software-factory-canary, or of the
org itself for a trial about the org and its Apps (decision 0035), or, for a trial of a vendor's
CLI, in no repo (decision 0033), and what came back, with every credential removed. The fake
GitHub in `sim/` is held to these (`sim/grounding.py`). How a trial is run is the skill
`.claude/skills/run-a-platform-trial/SKILL.md`; P-13's script, `tools/trial_p13_cli.sh`, has its runbook beside it, `tools/trial_p13_runbook.md`.
P-26's script, `tools/trial_p26_sandbox.sh`, holds its runbook and its pass condition at its top; so do P-50's and P-51's, `tools/trial_p50_linux_sandbox.sh` and `tools/trial_p51_sandbox_writes.sh`,
which with P-50's stub, `tools/trial_p50_stub.py`, a trial runs only in the canary's workflow; this repo's tests run them against a stand-in CLI, the stub on 127.0.0.1.
`python3 -m tools.check_trials` checks this folder alone, before a fixture is added to git.

| Rule | Held by |
|---|---|
| A fixture is `<trial>.json` or `<trial>.<what>.json`, validates against `schemas/trial.schema.json`, and records the trial it is named for. Nothing else is kept here | `tests/test_tools.py::test_a_fixture_that_is_misnamed_or_invalid_is_caught` |
| The trial ran in the canary repo, of the org `combsmith` (decision 0035), or, for a vendor's CLI, in no repo (decision 0033) | `examples/invalid/trial.run-outside-the-canary.json`, `examples/invalid/trial.neither-the-canary-nor-the-org.json` |
| No credential: no field named for one at any depth, no string shaped like one, plainly or in base64. Delete it and list where in `removed` | `tests/test_tools.py::test_a_credential_in_a_fixture_is_caught` |
| A header is kept only if `HEADERS` in `tools/check_trials.py` names it | `tests/test_tools.py::test_a_header_a_fixture_may_not_keep_is_caught` |
| The examples of a fixture, counter-examples too, and this file hold no credential either | `tests/test_tools.py::test_every_example_of_a_fixture_and_the_folder_notes_are_scanned` |
| A raw capture is redacted by `tools/redact_trial.py`, outside the repo, before it is read; what comes out passes the rules above | `tests/test_tools.py::test_a_raw_capture_comes_out_with_no_credential` |
| Nothing reads the canary at run time: only a document, a fixture, its example and schema, and the Apps' installs in `config/apps.json` name it. A fixture arrives by pull request | `tests/test_tools.py::test_code_that_reads_the_canary_is_caught` |
| A fixture keeps GitHub's words as said, so it alone may name a model or the proof of concept's private repo | `tests/test_tools.py::test_only_a_fixture_may_name_a_model_or_the_proof_of_concept` |
| A rule of the fake grounded here names a valid fixture of a trial that asks it | `tests/test_tools.py::test_a_fixture_named_for_a_rule_must_exist_and_validate` |
| `repo` is null exactly when every request asks as `subscription`, as a trial of a vendor's CLI does (decision 0033) | `tests/test_tools.py::test_a_null_repo_goes_with_a_subscription_and_nothing_else` |
| `repo` is the org exactly when every call is a REST call of an App, the org or an installation, climbing nowhere (decision 0035) | `tests/test_tools.py::test_the_org_is_the_repo_exactly_when_every_call_is_of_the_org_or_its_apps` |
| Whoever asked is named in words, never by an address | `tests/test_tools.py::test_an_asker_named_by_an_address_is_caught` |
| A canary fixture reads the org's repos alone and is answered with them, an App's read within its reach; a write is one of `WRITES`, on a node a read of the canary answered | `tests/test_tools.py::test_a_cost_measurements_exchanges_name_each_repo_they_span` |
| P-13's script gives the CLI only the environment it names, and no tool | `tests/test_tools.py::test_the_cli_is_given_only_the_named_environment_and_no_tool` |
| It refuses the default configuration: the home directory, any directory holding it, anything under `~/.claude`, the repo | `tests/test_tools.py::test_each_refusal_stops_before_anything_is_asked` |
| It stops unless `auth status` exits 0 and says logged in, and records that exit code | `tests/test_tools.py::test_the_logins_exit_code_is_recorded` |
| Of the Task's answer only the fields the script names reach OUT, so no model text does, whether or not the structured output validates | `tests/test_tools.py::test_no_model_text_reaches_out_whether_or_not_the_output_validates` |
| P-26's script gives the CLI only the environment it names, its markers and one command | `tests/test_tools.py::test_the_cli_is_given_only_the_named_environment_and_one_command` |
| Its probe reads no process above the CLI | `tests/test_tools.py::test_the_probe_reads_nothing_above_the_cli` |
| No marker and none of the model's text reaches its OUT | `tests/test_tools.py::test_no_marker_and_no_model_text_reaches_out` |
| Each configuration is judged by the condition written first | `tests/test_tools.py::test_each_configuration_is_judged_by_the_condition` |
| P-50's script gives the CLI the stub, a dummy key and its markers alone | `tests/test_tools.py::test_the_cli_is_given_the_stub_a_dummy_key_and_the_markers_alone` |
| Its stub answers one tool call, then done, and keeps no header or prompt | `tests/test_tools.py::test_the_stub_answers_one_tool_call_and_keeps_no_header` |
| A Task that fails says why in the log, its markers taken out | `tests/test_tools.py::test_a_task_that_fails_says_why_in_the_log_without_its_markers` |
| P-51's script gives each configuration its scrub alone and a configuration directory of its own | `tests/test_tools.py::test_each_configuration_is_given_its_scrub_alone_and_a_directory_of_its_own` |
| Each configuration and order is judged by the condition written first, and nothing written outside is left | `tests/test_tools.py::test_each_configuration_and_order_is_judged_by_the_condition` |
