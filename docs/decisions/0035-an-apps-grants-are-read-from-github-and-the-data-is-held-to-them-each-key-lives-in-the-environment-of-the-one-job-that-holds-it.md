# 0035. An App's grants are read from GitHub and the data is held to them; each key lives in the environment of the one job that holds it

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
as it pairs no repo with a subscription: `repo` is `combsmith` exactly when every call is a REST
call of an App (`/apps/…`), the org (`/orgs/combsmith/…`) or an installation (`/installation/…`),
whose path has no segment that climbs out of it (`.` or `..`, plainly or percent-encoded).

`config/apps.json` gives each App its `app_id` and a `key` of `{environment, secret}`, a name and
never a value. `tools/check_apps.py` holds the data to P-39's fixtures, every condition of the pass
above: each fixture's verdict is `pass` and each of its reads was answered 200; each App's
registration and its installation are of its `app_id` and name, with exactly the data's permissions
and levels and no events; the installation is on `selected` repos; and it reaches exactly
`installed_on`. A list is held only if it was read whole: one page with no `link` header, each item
once, as many as its `total_count`. Without a record of any of them it trusts nothing. It holds each App's key to the environment of the job that holds it, by a fixed
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
| Each installation receives no event and is on `selected` repos | `tests/test_tools.py::test_an_installation_with_events_or_on_every_repo_is_caught` |
| Each App's registration is of its `app_id`, with exactly the data's permissions and levels and no events; an unread registration is not trusted | `tests/test_tools.py::test_the_registration_is_held_to_the_data_as_the_installation_is` |
| Each fixture of P-39 has the verdict `pass` | `tests/test_tools.py::test_a_fixture_of_p39_that_failed_is_not_trusted` |
| Each installation reaches exactly `installed_on`, by a selection of `selected`; an unread reach is not trusted | `tests/test_tools.py::test_the_repos_each_installation_reaches_are_exactly_installed_on` |
| A read GitHub answered with anything but 200 is not trusted, and neither is a list not read whole: one page of more, short of its count, or naming an item twice | `tests/test_tools.py::test_a_read_github_refused_is_not_trusted`, `tests/test_tools.py::test_a_list_not_read_whole_is_not_trusted`, `tests/test_tools.py::test_an_app_listed_twice_among_the_installations_is_caught` |
| Each App's key is kept in the environment of the job that holds it, under a secret named for the App: the Controller's and the reader's swapped are refused | `tests/test_tools.py::test_each_apps_key_is_kept_in_the_environment_of_the_job_that_holds_it` |
| Every Role's App key is kept in `apply`'s environment, which several Roles' keys may share | `tests/test_tools.py::test_every_roles_key_is_kept_in_applys_environment_and_they_may_share_it` |
| A key is named by its environment and its secret, in an environment a job holds | `examples/invalid/apps.a-key-in-an-environment-no-job-holds.json` |
| A fixture of P-39 holds no credential and no header a fixture may not keep | `tools/check_trials.py` |
| A fixture's `repo` may be the org, `combsmith`, as well as the canary; any other name is refused | `examples/invalid/trial.neither-the-canary-nor-the-org.json` |
| `repo` is the org exactly when every call is of an App, the org or an installation: a fixture of the org that asks of a repo is refused, and so is one that asks only of the org and records the canary | `tests/test_tools.py::test_the_org_is_the_repo_exactly_when_every_call_is_of_the_org_or_its_apps`, `tests/test_tools.py::test_a_call_of_a_repo_in_a_fixture_of_the_org_is_one_problem_whoever_asked` |
| A fixture of the org asks by REST, of this org alone, by a path that climbs nowhere | `tests/test_tools.py::test_a_fixture_of_the_org_asks_by_rest_of_this_org_alone_and_climbs_nowhere` |
| A trial of repos records the canary as its home; a measurement's reads may span the org's repos, each read naming its owner in its variables, its query or its path, every repo an answer names the org's, a read the App made naming and answered with only repos its installation reaches, and a command-line read the Maintainer's, as `trials/P-8.json` and `trials/P-32.json` do (the ruling of 2026-10-20 on "Trial P-8 (pass) and P-32 (fail): a pass sized to the counts costs 149 points, 1,788 an hour at the schedule; an App reads an owner as a contributor", pull request two hundred and twenty) | `tests/test_tools.py::test_a_cost_measurements_exchanges_name_each_repo_they_span` |
| A trial whose question is a read beyond the org's repos and its App's reach, `trials/P-4.json`'s repository subset and `trials/P-27.json`'s forks, names only the org's repos and the forks of the canary, and a command-line read there may be a fork's owner's (the working rulings on "Trials P-27, P-14, P-4, P-9 and P-20", issue one hundred and eighty-seven) | `tests/test_tools.py::test_a_cost_measurements_exchanges_name_each_repo_they_span` |
| Only the job that holds a key names its environment | `tests/test_tools.py::test_a_key_and_its_environment_are_named_by_their_one_file` |
| The machine user's token, a credential that is no App's, is held by `factory-approve` alone, which holds nothing else (decision 0055) | `tests/test_tools.py::test_the_approving_act_holds_the_approvers_token_alone`, `tests/test_tools.py::test_a_key_and_its_environment_are_named_by_their_one_file` |
