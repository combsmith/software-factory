# 0077. The grants of 2026-10-27 are read again by P-39 and mapped, and P-52 shows where the org's Pause can be read

Status: accepted. The orchestrator's story of 2026-10-27, after the Maintainer's App sitting: trial P-52 run at his
terminal and P-39's grants read again. It meets what decisions 0054, 0056, 0059 and 0060 waited on, the grants, and
leaves each of them otherwise as it is.

## Decision

| What | Decided | Because |
|---|---|---|
| P-39 read again | `trials/P-39.grants.json` is the registrations and installations as GitHub listed them on 2026-10-27, through the Maintainer's login, nothing minted. `trials/P-39.reach.json` stands: no installation's repos changed | `tools/check_apps.py` holds the data to what P-39 recorded |
| The controller | Gains `actions_variables` at read, for `read:pass.pause`, and `issues` at write, for `write:tracking_issue` and `read:facts.acceptance`. So the pass's token reads the Pause and a pull request's closing issues, and the effects step's token writes the tracking issue and reads the Pause again before a dispatch | Decision 0060's reads refused until the grants; decision 0056's tracking issue |
| The review Role's App | Gains `checks` at write, for `effect:create_check_run` and `read:facts.checks`; `actions` at read, for the run records; `issues` at read, for `read:facts.acceptance`; and `actions_variables` at read, for `read:pass.pause`, which the Maintainer granted later the same day and P-39 read. Its grants serve every read `apply` makes again, and `roles/pr-review.json` permits `create_check_run` | Decisions 0054 and 0059: the pull request that records the grant maps the needs and adds the Effect |
| `actions_variables` | GitHub's own name for the Variables permission, as the registration, the installation and the token each answered it, is a permission the schema allows | A name not in the schema is refused |
| P-52 | Passed on 2026-10-27 (`trials/P-52.json`): with Variables at repository read alone, the token reads the repo's `FACTORY_PAUSED`, and the org's as the repo's list of the org's variables names it; the org's own endpoint answers 403, asking for the organization's Variables permission. The fake's Pause is grounded on it | No organization permission is asked for: the repo's list reads what the repo's workflows see |
| The org's Pause in the pass | Still asked at the org's own endpoint by `adapters/pause.py`, so it reads unreadable on every pass and nothing is admitted until "Pause: read the org's FACTORY_PAUSED through the repo's list of org variables, as P-52 found" (issue 362) moves the read to the repo's list, where a list read whole that does not name it is unreadable, never unset: the org's variable is shared with every repo the Factory serves, and a repo it is not shared with stays idle. `apply` reads the Pause again with its own App's token, and refuses on a Pause it cannot read: issue 362 builds that read, on the grant recorded here (the orchestrator's rulings of 2026-10-27) | Not one line, so not folded in here; it fails closed meanwhile |

## Why

The Maintainer's sitting of 2026-10-27 changed two Apps' registrations, and `tools/check_apps.py` holds the data to
what P-39 last read, so the grants are read again and mapped in one change. P-52 asked whether the controller's
token reaches the Pause before a need is written for it; it reaches the repo's, and the org's only through the
repo's list. A narrowed mint in the second machine-user window, P-52b, whose fixture comes with that window's,
answered `actions_variables` as asked, so the name the pass asks for is one GitHub takes in a token request.

## Boundaries

| Boundary | Check |
|---|---|
| The data agrees exactly with what P-39 read on 2026-10-27 | `tools/check_apps.py` |
| The review Role's App is granted what `apply` reads again, and the check run's write | `tests/test_apply.py::test_the_role_app_is_granted_what_apply_reads_again`, `tests/test_apply.py::test_the_role_app_is_granted_checks_to_write_its_check_run` |
| An Effect whose need waits writes nothing and mints nothing | `tests/test_apply.py::test_nothing_is_minted_for_a_refused_result_and_the_token_is_revoked_whatever_happens` |
| The repo's Pause is read as P-52 recorded GitHub's answer | `tests/test_effects.py::test_the_pause_is_read_as_github_holds_the_variable` |
| The org's Pause is read through the repo's list of the org's variables | `tests/test_effects.py::test_the_orgs_pause_is_read_through_the_repos_list_of_the_orgs_variables` |
| The effects step's token reads the Pause it reads again | `tests/test_steps.py::test_the_controller_mints_from_its_key` |
| The fake's Pause names P-52, whose row asks it | `tools/check_trials.py` |
| Each of these grants has a mutant that a test kills | `tools/mutants.py` |
