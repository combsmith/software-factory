# 9999. A Role that pushes waits for GitHub's reset in its App's installation

Status: accepted. 2026-11-26, the Solution Architect; issue 838. Extends decision 1224's faults and pull request 1252's `push_rate_limited`; parts 1 and 2 are pull requests in the same issue.

## Decision

`outcome/1` gains the fault `github_capacity` and an optional `github_reset`, GitHub's `x-ratelimit-reset`. The run record carries it, and when the Run ended (`adapters/records.py`).

The pass gives the Kernel `github_deferred`: each Role and repo owner whose Run ended so, until the latest reset. A reset is held between `least_seconds` and `most_seconds` after the Run ended; a missing one waits `most_seconds`. Owners are one in any case (`github_deferred` in `controller/pass_.py`, `config/controller.json`).

The Kernel defers a pushing Role's Run, while its Role and owner wait, as `github_capacity` (`kernel/derive.py`). A Role pushes where its manifest permits `push_commits`, as `tools/check_authority.py` holds (`configuration.pushers`). No other Run waits. It spends no attempt, counts toward the Run ceiling, and never sets `model_deferred_until`. It is no whole-scope deferral, so its items may go stale.

The scope is what GitHub counts the push token against. P-71 asked with a person's token, but the push sends the Role App's installation token (`adapters/identity.py`). Each Role has its own App, so the Role and the owner name it.

Limits: no Role pushes, and nothing writes the fault, until the Harness's push step does. A list of pushers that cannot be read defers every Run. A Run with no end waits from its start; a later `updated_at` moves the wait. The approving act's reread sees its own item's Runs alone (decision 0199).

## Why

A rate limit is GitHub's, not the item's or the model's. Retried at once, each push spends a Run; under `capacity` every model Run would wait five hours.

The reset is no outside text reaching a decision. It is a number, never text, and reaches only the Controller's clamp, never a Kernel reason. `outcome/1` refuses one that is no whole number, and the Harness then writes `environment` (`harness/outcome.py`). The clamp bounds the worst a wrong value does.

## Boundaries

| Boundary | Check |
|---|---|
| A pushing Role's Run waits in its own installation until the reset, and at it is admitted | `tests/test_decide.py::test_a_pushing_roles_run_waits_in_its_installation_until_the_reset`, `kernel/derive.py`, mutant: "another installation's wait for GitHub holds" |
| A Role that does not push never waits; for one that does, an unreadable wait defers | `tests/test_decide.py::test_a_wait_or_a_list_of_pushers_that_cannot_be_read_defers_a_pushing_role_alone`, `kernel/derive.py`, mutant: "a Role that does not push waits for GitHub too" |
| The same on an issue | `tests/test_issue.py::test_the_pause_capacity_and_concurrency_defer_a_run`, `kernel/issue.py`, mutant: "an issue's Run is given no Role that pushes" |
| A Run GitHub limited is no attempt | `tests/test_decide.py::test_a_run_github_limited_is_no_attempt`, `kernel/brakes.py`, mutant: "a Run GitHub limited is an attempt" |
| The Roles that push come from their manifests' grant | `tests/test_controller.py::test_the_kernel_is_given_the_roles_granted_the_push_from_their_manifests`, `controller/configuration.py`, mutant: "a Role granted no push is given as one that pushes" |
| A reset past the cap waits the cap, one in the past the least wait, and a non-number the cap | `tests/test_controller.py::test_a_github_limit_defers_a_pushing_roles_runs_in_its_installation_until_its_reset`, `controller/pass_.py`, mutant: "GitHub's reset is not held to the most wait" |
| The model's deferral is never set, and a short read gives no waits | `tests/test_controller.py::test_a_github_limit_defers_a_pushing_roles_runs_in_its_installation_until_its_reset`, `controller/pass_.py`, mutant: "the waits for GitHub are given from a list read short" |
| The records port reads the reset with the outcome, keeps it, and says when a Run ended | `tests/test_adapters.py::test_githubs_reset_is_read_with_the_outcome_and_kept_and_a_completed_run_says_when_it_ended`, `adapters/records.py`, mutant: "GitHub's reset is not kept from the record before" |
