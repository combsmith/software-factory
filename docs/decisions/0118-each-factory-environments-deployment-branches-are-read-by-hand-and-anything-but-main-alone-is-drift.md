# 0118. Each factory environment's deployment branches are read by hand, and anything but `main` alone is drift

Status: accepted. On "Each factory environment's deployment branches are read at run time" (issue 463), found by the security read of the release App's pull request. It names the live read that `docs/decisions/0114-the-release-app-is-in-the-data-and-alone-holds-workflows.md` says is needed.

## Decision

| What | Decided | Because |
|---|---|---|
| The read | `tools/environments_drift.sh` reads every environment of this repo through whoever is logged in to gh, by hand, as `tools/rulesets_drift.sh` reads the rulesets | The issue allows this or the Controller's pass. A pass would need an App to hold a read of environments, which none does: `config/apps.json` would change, and each App's grant is the Maintainer's |
| The rule | Each environment deploys from the branch `main` alone, through a list of its own, and admins cannot bypass it. The rule is in `tools/environments_drift.py`, and no file records what GitHub answered | It is one rule for all of them, so a file would add a place for it to differ, and would say only what it was the day it was read |
| Which | Every environment GitHub lists, and each the repo says holds a key, as a workflow's job, a stored credential's or an App's, must exist. One the repo does not name is held all the same | So a new one is noticed. `factory-queue`, which an App's row names and no workflow yet, is among them |
| The one left out | `factory-next`, which a Deployment makes and which holds no key. If the repo ever names it for a key, that is drift | `adapters/deployments.py` records a Release's move there, and no job runs in it |
| When it is run | By hand, in the `cut-a-release` skill's steps, and whenever the Maintainer wants. Nothing makes anyone run it, so a change is noticed at the next read and not when it is made | A live read in CI would need the same grant |
| What it reads | The list and each environment's policies, redacted outside the repo. No secret, and no list of secrets | The repo's rule that a secret's value is never read |

## Why

An environment's deployment branches keep its keys from another ref's copy of a workflow, and `factory-release`'s key holds `contents` and `workflows` write. Read on 2026-11-02, all seven environments were `main` alone, and admins could bypass none.

## Boundaries

| Boundary | Check |
|---|---|
| Anything but `main` alone, or an admin's bypass, on the first, the release's and the last environment, is drift | `tests/test_tools.py::test_a_deployment_policy_other_than_main_alone_is_drift` |
| An environment the repo names and GitHub lacks is drift, one it does not name is held, and the Deployment's alone is left out | `tests/test_tools.py::test_an_environment_the_repo_names_or_gets_wrong_is_drift` |
| The repo's list is whole, or that is drift | `tests/test_tools.py::test_a_list_not_read_whole_is_drift` |
| The script reads only, redacts each answer, leaves nothing and refuses a scratch inside the repo | `tests/test_tools.py::test_the_script_reads_each_environment_redacts_it_and_compares`, `tests/test_tools.py::test_a_scratch_directory_inside_the_repo_is_refused_however_it_is_reached` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
