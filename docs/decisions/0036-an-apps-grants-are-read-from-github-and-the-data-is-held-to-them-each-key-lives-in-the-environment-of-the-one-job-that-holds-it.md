# 0036. An App's grants are read from GitHub and the data is held to them; each key lives in the environment of the one job that holds it

Status: accepted. Taken as a working ruling on 2026-10-17, which the Maintainer may overturn in review, for
"Three Apps registered and installed, and their real grants compared with the data" (issue 26). It
decides one row of decision 0033 otherwise: a fixture's `repo` is the canary or null, and may now also
be the org, `combsmith`, for a trial whose every call is of an App, the org or an installation.

## Decision

What GitHub granted each Factory App is read from GitHub, as trial P-39, a row of §6 in batch 1.
Three reads, in order. `GET /apps/{slug}` for each App gives its registration, and
`GET /orgs/combsmith/installations` gives what each installation accepted, kept whole with
third-party Apps included; both are read through the Maintainer's login and mint nothing. Which
repos each installation reaches needs an installation token, so `tools/trial_p39_reach.sh` reads
`GET /installation/repositories` at the Maintainer's terminal, with a token minted from the App's
local key, narrowed to `metadata: read`, used once and revoked. Only that response is captured,
outside the repo, and only its redacted copy leaves the script. No session runs it.

P-39 passes when, for each App: `app_id` is the data's; the permissions and their levels are
exactly the data's, no more and no fewer, and the same registered and installed; `events` is empty;
the selection is `selected`; and the repos are exactly `installed_on`. A mismatch is a fail, and no
key for that App is stored: the Maintainer corrects the registration and the trial runs again, and
only the passing fixture is kept. If GitHub cannot grant what the data asks, the data changes by
pull request, with an issue against the design. The first two reads are kept in
`trials/P-39.grants.json` with a verdict of their own, and the third in a fixture of its own,
P-39.reach.json, since a fixture must carry a verdict and the reach is read later, elsewhere. P-39
passes only if both do. Its reads are of the org and its Apps, not of a repo, so its fixtures record
`repo` as the org, `combsmith`: the trial schema accepts the canary, the org, or no repo for a
trial of a vendor's CLI, and nothing else. `tools/check_trials.py` pairs the org with what was asked,
as it pairs no repo with a subscription: `repo` is `combsmith` exactly when every call is of an App
(`/apps/…`), the org (`/orgs/combsmith/…`) or an installation (`/installation/…`).

`config/apps.json` gives each App its `app_id` and a `key` of `{environment, secret}`, a name and
never a value. `tools/check_apps.py` holds each App's permissions and levels to what P-39 recorded
for the installation of that `app_id`, which must be of the App so named; with no such record it
trusts nothing. It holds each App's key to the environment of the job that holds it, by a fixed
map: the Controller's key to the poller's, `factory-poller`; the reader's to `run`'s, `factory-run`;
and every other App's, each a Role's, to `apply`'s, `factory-apply`, as §4.9 gives `apply` each
Role's App key. Several Roles' keys may share `factory-apply`, and no other environment holds two.
The secret is named for the App, as `CONTROLLER_APP_KEY` for `controller`. The trial-author App is
not Factory data, and its id stays in fixtures.

Each job that holds a key has an environment of its own on the Factory's repo: `factory-poller`
holds `CONTROLLER_APP_KEY`, `factory-apply` holds `PR_REVIEW_APP_KEY` and `factory-run` holds
`READER_APP_KEY`. Each has a deployment branch policy that allows `main` alone, admin bypass off,
and no required reviewer. The Maintainer stores each key himself, and only for an App that passed.

## Why

Two files typed by hand agreeing with each other prove nothing about what GitHub granted; the data
says what each need takes, and only a checked grant gets a key. Without the check the data drifts
from GitHub and the two hand-typed files agree again. Reach needs an installation token, so it runs
where the keys are, and the session reads only what is redacted. A job that names an environment
reads all its secrets, so one shared environment would hand `run`, which reads untrusted text, a key
that can write (decision 0004, §4.9). There is no reviewer on an environment because the Factory
runs unattended, and P-3 showed that the branch policy holds.

## Boundaries

| Boundary | Check |
|---|---|
| Each App's permissions and levels in the data are exactly those GitHub granted the installation of its `app_id`, which is of the App so named | `tests/test_tools.py::test_the_data_is_held_to_what_github_granted_each_app` |
| With no record of what GitHub granted, the data is not trusted | `tests/test_tools.py::test_with_no_record_of_what_github_granted_the_data_is_not_trusted` |
| Each App's key is kept in the environment of the job that holds it, under a secret named for the App: the Controller's and the reader's swapped are refused | `tests/test_tools.py::test_each_apps_key_is_kept_in_the_environment_of_the_job_that_holds_it` |
| Every Role's App key is kept in `apply`'s environment, which several Roles' keys may share | `tests/test_tools.py::test_every_roles_key_is_kept_in_applys_environment_and_they_may_share_it` |
| A key is named by its environment and its secret, in an environment a job holds | `examples/invalid/apps.a-key-in-an-environment-no-job-holds.json` |
| A fixture of P-39 holds no credential and no header a fixture may not keep | `tools/check_trials.py` |
| A fixture's `repo` may be the org, `combsmith`, as well as the canary; any other name is refused | `examples/invalid/trial.neither-the-canary-nor-the-org.json` |
| `repo` is the org exactly when every call is of an App, the org or an installation: a fixture of the org that asks of a repo is refused, and so is one that asks only of the org and records the canary | `tests/test_tools.py::test_the_org_is_the_repo_exactly_when_every_call_is_of_the_org_or_its_apps` |
| Only the job that holds a key names its environment | waiting on `harness/` |
