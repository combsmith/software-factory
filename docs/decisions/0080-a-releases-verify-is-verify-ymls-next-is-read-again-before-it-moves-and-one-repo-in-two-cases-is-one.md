# 0080. A Release's verify is verify.yml's, next is read again before it moves, and one repo in two cases is one

Status: accepted. The Factory Builder's rulings of 2026-10-27, which the Maintainer may overturn in review, on the second-family reads of the pull requests that built the Release code, read by Muse while the other family's reviewer had no quota. It extends `docs/decisions/0071-a-release-is-cut-from-main-through-the-eval-gate-and-never-moved-and-next-is-rolled-back-with-no-gate.md`, `docs/decisions/0073-the-release-step-reads-its-facts-and-the-eval-gate-through-the-release-apps-token-writes-each-tag-and-reads-it-back.md` and `docs/decisions/0076-one-workflow-moves-next-held-to-its-shape-through-the-release-apps-token-for-this-repo-alone.md`.

## Decision

| What | Decided | Because |
|---|---|---|
| Which `verify` counts | `adapters/candidate.py`'s `verified` counts only the check the Kernel's `verify` Lens counts: named `verify`, from GitHub Actions (App 15368), run by `.github/workflows/verify.yml`, the three read from `config/defaults.json` in a test. The workflow is read by the check run's suite: `GET /repos/{repo}/actions/runs?check_suite_id={id}`, whose one run must be of that file, that commit and that suite. Any other workflow's job of that name, a suite that cannot be read, or one of two runs, is no `verify`, and the gate stays closed | A job named `verify` in any workflow on `main` reports a check of that name from the same App; the Kernel's Lens is pinned to its workflow file, and the Release's gate was not |
| `next` read again | Just before it moves `next`, the release step reads the Release tags again, and stops, `channel_moved`, where `next` is no longer where the plan read it, moving nothing; a cut's Release, already created and read back, stays. A read that fails there is `refs_unreadable` | The plan is made of the first read. A step run beside it is already kept out by the workflow's one-at-a-time concurrency (0076); a person can still move the tag |
| The gap accepted | A tag moved by hand between that read and the step's own write is not seen: a ref's update compares nothing, so no read can close the gap. The read-back after the write still holds the Channel to its planned commit | GitHub's refs API has no compare-and-swap |
| One repo in two cases | `tools/check_release.py`'s ring check reads a served repo whatever its case: one repo spelled two ways, on two Channels, is one repo served by two | GitHub names a repo whatever its case |
| The rest | No rule changes: each reading the second-family reads found unheld is held by a test and a mutant. The step run with no argument, as the workflow runs it; the read-back's Channel on its commit; the four names only `.github/workflows/release.yml` may hold, each named elsewhere; a step of bare text, and a `with:` given a text, in `.github/workflows/release.yml`; a Run whose Release moved and whose token GitHub did not revoke, which leaves no outcome; and the status of each answer `adapters/candidate.py` and `adapters/deployments.py` read, and the eval set's manifest by its type, path, encoding, size and bound | The repo's rule: every rule has a test and a mutant that the test kills |

## Why

The pull requests that built the Release code were read by one model family. A read by the other, run on each merge
commit against its parent, found a gate that trusted a check's name over its workflow, a plan not read again before
its write, a ring check that missed one spelling, and readings no test held.

## Boundaries

| Boundary | Check |
|---|---|
| A `verify` counts only from `.github/workflows/verify.yml`, as the Kernel's Lens reads it, and only as a 200 answers it | `tests/test_release_step.py::test_verify_counts_only_from_verify_yml_as_the_kernels_lens_reads_it`, `tests/test_release_step.py::test_verify_counts_only_as_github_actions_one_success_on_the_commit` |
| The eval set's manifest is read only as the file it names, within its bound | `tests/test_release_step.py::test_the_sets_manifest_is_read_only_as_the_file_it_names` |
| `next` moved since the plan stops the step before it moves, `channel_moved` | `tests/test_release_step.py::test_next_moved_since_the_plan_stops_the_step_before_it_moves` |
| A Channel not on its commit after the move is not read back | `tests/test_release_step.py::test_a_channel_not_on_its_commit_after_the_move_is_not_read_back` |
| The step runs with no argument, as the workflow calls it | `tests/test_release_step.py::test_the_step_runs_with_no_argument_as_the_workflow_calls_it` |
| A Deployment is made only as GitHub answers it made | `tests/test_release_step.py::test_a_deployment_of_next_is_recorded_with_its_status` |
| One repo in two cases on two Channels is refused | `tests/test_release.py::test_no_repo_and_family_is_served_by_two_channels_and_both_are_of_one_major` |
| Each name only `.github/workflows/release.yml` may hold, named in another workflow, is refused | `tests/test_release_workflow.py::test_only_release_yml_names_the_release_jobs_environment_key_token_or_step` |
| A step of bare text, and a `with:` given a text, are refused in `.github/workflows/release.yml` | `tests/test_release_workflow.py::test_each_counter_example_is_refused_for_its_one_fault` |
| A Run whose Release moved and whose token was not revoked leaves no outcome | `tests/test_steps.py::test_a_run_on_another_release_than_its_pass_builds_no_task` |
| An empty `with:` on the step that takes none, and a step of text after the steps' keys, are refused in `.github/workflows/release.yml` | `tests/test_release_workflow.py::test_each_counter_example_is_refused_for_its_one_fault` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
