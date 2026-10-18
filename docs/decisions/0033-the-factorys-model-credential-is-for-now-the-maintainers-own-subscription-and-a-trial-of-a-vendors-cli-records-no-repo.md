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
`subscription` for `as.kind`, and nothing more. The schema cannot say that `subscription` goes with
a null `repo` and with nothing else: its validator, `tools/jsonschema_lite.py`, has no conditional
keyword. So a `subscription` request in a fixture of the canary validates, and no counter-example
can show that it should not.

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
| A fixture's `repo` is the canary or null, never another repo | `examples/invalid/trial.run-outside-the-canary.json` |
| A subscription is named in words, never by its address | `examples/invalid/trial.a-subscription-named-by-its-address.json` |
| A fixture of a vendor's CLI holds no credential and no header a fixture may not keep | `tools/check_trials.py` |
| The Factory's model credential is its own again, held by the `run` job as an environment secret | waiting on `harness/` |
