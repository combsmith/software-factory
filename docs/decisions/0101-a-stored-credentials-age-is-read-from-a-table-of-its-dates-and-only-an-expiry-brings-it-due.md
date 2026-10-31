# 0101. A stored credential's age is read from a table of its dates, and only an expiry brings it due

Status: accepted. "Credentials: each stored credential's age read, and one alert near its limit (L-37)" (issue 305),
under the orchestrator's rulings and the Maintainer's answers of 2026-10-29.

## Decision

| What | Decided | Because |
|---|---|---|
| The table | `config/credential-ages.json`, `credential-ages/1`, one row for each secret the Factory stores, by its name alone: its kind, where it is stored, the workflow files that name it, `rotated_on`, whether it `expires`, `expires_on` and `rotate_every_days`. It is not named credentials.json, as the issue drafted it: the org's secrets baseline in `.gitignore` ignores every file of that name | The age is read from the Release's own data, which a pull request changes and a test can read. Nothing reads a secret, its list or its value at run time, so no App is granted a secrets read |
| The source of each date | `rotated_on` was read once from GitHub's `updated_at` for each of this repo's credentials, whether stored in an environment or the organisation: names and times alone, never a value, never another repo's. Each expiry is the day the Maintainer set, never one read from GitHub: 2026-12-31 for `HELDOUT_TOKEN` and `CLAUDE_CODE_OAUTH_TOKEN` ("Make it 12/31/2026", in chat, 2026-10-30). He updates the row by pull request at each rotation | The orchestrator's ruling R6. A row he forgets is caught by its alert, early and never late |
| The limit | The earlier of `expires_on`, where the credential `expires`, and `rotated_on` plus `rotate_every_days`, where it has a period, at the start of that day in UTC. One with neither has no limit and never falls due by age. A date is read only where it can bring the credential due: `rotated_on` only for a period, and otherwise it is the record of a rotation. No credential has a period: only `HELDOUT_TOKEN` and `CLAUDE_CODE_OAUTH_TOKEN` expire, and every App key, `APPROVER_TOKEN` and `SONAR_TOKEN` is rotated on suspicion alone | The Maintainer's choice, 2026-10-29: expiry alone, no rotation periods. This departs from section 4.9's "on a fixed period" for the machine user's token and each App's key |
| The alert | `controller/credentials.py`, pure, called by the pass with the table and `now`. One alert, `credential_due`, when any limit is 14 days away or less, `due_within_days`. The pass record and the health view name each by its secret in `credentials_due`; the tracking issue carries the code alone, as it carries every cause. A row that cannot be read is due, and one that `expires` with no `expires_on` given is such a row; a table that cannot be read is due whole. With the dates above the first pass raises nothing; the alert first stands at the first pass from 2026-12-17, fourteen days before them | L-37: the age of each credential is read, and one near its limit raises one alert (L-48, one cause one alert) |
| When it clears | At the first pass that reads the updated row. The pass reads the table at the Release's channel, `factory/v0-next`, so that is the first pass after the row reaches the channel, not after its merge | The pass reads its configuration from the Release (decision 0006) |
| A coordinate | `HELDOUT_OWNER` and `HELDOUT_REPO` are rows of kind `coordinate`, with no dates, never due. One given a date is read as a credential mislabelled, and is due | A value kept secret so that a log masks it is no credential and has no age (decision 0053), and every secret a workflow names still has a row |
| The drift | `tools/check_workflows.py` holds that every secret a workflow names has a row, and each row lists exactly the workflow files that name it: one, but the model's credential, which `.github/workflows/eval.yml` and `.github/workflows/run-jobs.yml` name (decision 0053), and none for `QUEUE_APP_KEY` until the queue App's workflow is built. An App's key is kept where `config/apps.json` says alone (decision 0009), and is `write` if its App writes anything. GitHub's minted `GITHUB_TOKEN` has no row | The orchestrator's ruling R2. A new secret without its row, or a row whose workflow has gone, fails the check |
| The kinds | `write`, `model`, `read`, `coordinate`. `RELEASE_APP_KEY` is `write`, its environment in its row since `config/apps.json` has no release App. `SONAR_TOKEN` is `read`, since it writes nothing on GitHub; like the model's credential, it is an organisation secret | Unverified: how the job boundary should class `SONAR_TOKEN`, which writes analyses to SonarCloud |

## Why

A credential that lapses shows today only as a refusal on the next run. The table makes each one's age a fact the
pass reads, and the alert says which, two weeks before.

## Boundaries

| Boundary | Check |
|---|---|
| A credential within `due_within_days` of its limit, or whose row cannot be read, is one alert, named in the pass record and the health view | `tests/test_controller.py::test_a_credential_near_its_limit_raises_one_alert` |
| Every secret a workflow names has a row, and each row lists exactly the workflows that name it | `tests/test_tools.py::test_every_secret_a_workflow_names_has_a_row_and_each_row_names_its_workflows` |
| A date that is no date, and a value written down, are refused | `examples/invalid/credential-ages.a-date-that-is-no-date.json`, `examples/invalid/credential-ages.a-value-written-down.json` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
