# 0076. One workflow moves next, held to its shape, through the release App's token for this repo alone

Status: accepted. PR 2b of "Release: cut an immutable tag, move next, and roll back in one action" (issue 197), under
its ruling 4′ and the orchestrator's rulings of 2026-10-26. It adds the workflow that runs the step decision 0073 built,
and leaves decisions 0071 and 0073 as they are.

## Decision

| What | Decided | Because |
|---|---|---|
| The workflow | `.github/workflows/release.yml`, `sf-release`: on the Maintainer's dispatch (`cut`, `move` or `rollback`, with a version or a target), and on a weekday schedule that cuts only when the repo's `FACTORY_RELEASE_AUTO` is true and no Pause is set | Ruling 4′; ruling 9′'s fifth step needs a move forward |
| Its one job | `release`, on the environment `factory-release`, granted `contents: read` alone, one run at a time and none cancelled; GitHub's own runner, at most 15 minutes | The environment's deployment branches, `main` alone, are what keep its key from another ref's copy of the file |
| The token | Minted by the pinned `actions/create-github-app-token`, for this repo alone, with contents, workflows and deployments write and actions and checks read | 4′'s grants, and checks read, which `adapters/candidate.py` needs to read `verify`'s check run: an App registered without it could mint no token, and even a rollback could not run |
| The checkout | The commit the run is of, never a ref an output names | CodeQL's untrusted-checkout rule; a cut is of that commit |
| The step | `python3 -m release.move` with no argument, given its inputs and the token under `env:` and nothing else; a cut with no version, as the schedule asks one, is of the next patch of `next`'s major, and none is named when a later major's Release exists | A workflow's run line is a module and nothing else; the schedule names no version |
| Its shape | `release_problems` in `tools/check_workflows.py` holds every line of it, its triggers word for word, as `eval_problems` holds the eval job's workflow; `SHAPED` spares it the shim rule alone. No other workflow names its environment, key, token or step | Ruling 4′ asked for it held by its hash; a shape check names each fault, where a hash names none |

## Why

The step and its ports were decision 0073's. This is the one workflow on a dispatch or a schedule that is not a shim,
since it cannot call the Release it moves. Nothing runs it until the Maintainer registers the release App with the
grants above, puts its key in `factory-release`, and the eval set holds cases.

## Boundaries

| Boundary | Check |
|---|---|
| `.github/workflows/release.yml` is held to its shape, each fault named | `tests/test_release_workflow.py::test_each_counter_example_is_refused_for_its_one_fault` |
| It keeps every workflow rule but the shim rule | `tests/test_release_workflow.py::test_the_live_file_is_the_shape_and_keeps_every_other_rule` |
| No other workflow names its environment, key, token or step | `tests/test_release_workflow.py::test_only_release_yml_names_the_release_jobs_environment_key_token_or_step` |
| A cut with no version is of the next patch, and none past a later major | `tests/test_release_workflow.py::test_a_cut_asked_with_no_version_is_of_the_next_patch_or_the_majors_first`, `tests/test_release_step.py::test_a_cut_asked_with_no_version_is_of_the_next_patch` |
| The release App's needs, checks read among them, wait on its registration | `tests/test_release.py::test_the_release_apps_needs_wait_on_its_registration` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
