# 0033. The Factory's model credential is, for now, the Maintainer's own subscription; a trial of a vendor's CLI records no repo

Status: accepted. Taken as a working ruling on 2026-10-18, which the Maintainer may overturn in review, for
"Trial P-13: the model CLI returns validated structured output on the subscription" (issue 15).

## Decision

For now, the Factory's model credential is the Maintainer's own subscription. It is logged in under
a configuration directory of its own, `~/.config/sf-factory-claude`, apart from the one his
interactive sessions use, and only the Factory uses that directory. This departs from the design.
§1.1 takes the credential as "a subscription of the Factory's own", and §4.9 counts on "a
credential that belongs to the Factory alone, so that theft is a rotation and not the loss of the
Maintainer's own account". Trial P-13 ran on this login.

Slice 1's CI credential reopens this decision. That is the credential the `run` job holds as an
environment secret, after P-3 and P-26. Until then no workflow holds this login, and no repo
stores it.

The same ruling decides how a trial is recorded when it asks a vendor's CLI and not GitHub, as P-13
does. Its fixture records `repo` as null. Each of its requests is made `as` the kind
`subscription`: the vendor account the CLI is logged in to. That account is named in words and
never by its address or a credential. `schemas/trial.schema.json` accepts null for `repo` and
`subscription` for `as.kind`, and nothing more. The schema cannot tie the two together, because
its validator, `tools/jsonschema_lite.py`, has no conditional keyword. So `tools/check_trials.py`
ties them, in a fixture and in an example alike:
- `repo` is null exactly when every request asks as `subscription`;
- a name that holds an `@` is refused as an address.

## Why

This is the Maintainer's choice. Whether automated use of a subscription is within the vendor's
terms is not confirmed (the comments on that issue, and §6.1, last paragraph). The Maintainer accepted
that risk. It costs this: if the credential is stolen, the Maintainer loses his own account, not
only a rotated credential. That is the loss §4.9's third layer was there to prevent. Its own
configuration directory keeps the Factory's use apart from his sessions, and makes it readable as
the Factory's. It does not make the account the Factory's.

A fixture names where a trial ran. A trial of a vendor's CLI ran in no repo, so the canary would
be false, and null is true. None of GitHub's kinds of actor is the vendor's account, so it is given
a kind of its own.

## Boundaries

| Boundary | Check |
|---|---|
| A trial that asks a vendor's CLI records `repo` as null, and asks as `subscription` | `examples/trial.a-vendors-cli.json` |
| `repo` is null exactly when every request asks as `subscription`: a null `repo` with any other kind is refused, and so is `subscription` with a repo | `tests/test_tools.py::test_a_null_repo_goes_with_a_subscription_and_nothing_else` |
| A fixture's `repo` is the canary or null, never another repo | `examples/invalid/trial.run-outside-the-canary.json` |
| Whoever asked is named in words, never by an address | `tests/test_tools.py::test_an_asker_named_by_an_address_is_caught` |
| A fixture of a vendor's CLI holds no credential and no header a fixture may not keep | `tools/check_trials.py` |
| P-13's script, `tools/trial_p13_cli.sh`, gives the CLI only the environment it names, and no tool; it refuses the default configuration (the home directory, any directory holding it, anything under `~/.claude`, the repo) and stops unless `auth status` exits 0 and says logged in, recording that exit code | `tests/test_tools.py::test_the_cli_is_given_only_the_named_environment_and_no_tool`, `tests/test_tools.py::test_each_refusal_stops_before_anything_is_asked`, `tests/test_tools.py::test_the_logins_exit_code_is_recorded` |
| Of the Task's answer only the fields the script names reach OUT, so no model text does, whether or not the structured output validates | `tests/test_tools.py::test_no_model_text_reaches_out_whether_or_not_the_output_validates` |
| The Factory's model credential is its own again, held by the `run` job as an environment secret | waiting on `harness/` |
| The context's test runs the CLI at the same pin, on the same login, from a configuration directory of its own, and holds no credential in its record | `tests/test_tools.py::test_a_run_is_judged_and_recorded_with_no_model_text` |
