# 9999. A Role that pushes waits for GitHub's reset in its App's installation

Status: accepted. 2026-11-26, the Solution Architect; issue 838. Extends decision 1224's faults and pull request 1252's `push_rate_limited`; parts 1 and 2 are pull requests in the same issue.

## Decision

`outcome/1` gains the fault `github_capacity`, with an optional `github_reset`: GitHub's `x-ratelimit-reset`, a whole number of seconds. The records port carries it to the run record, with when the Run ended (`adapters/records.py`).

The pass gives the Kernel `github_deferred`: each Role and repo owner whose Run ended so, until the latest reset. A reset is held between `least_seconds` and `most_seconds` after the Run ended; a missing or malformed one waits `most_seconds` (`github_deferred` in `controller/pass_.py`, `config/controller.json`).

The Kernel defers a Run of a Role that pushes, while its own Role and owner wait, as `github_capacity` (`github_waiting` in `kernel/derive.py`). The Roles that push are those whose manifest permits `push_commits`, the grant `tools/check_authority.py` holds (`configuration.pushers`). No other Run waits. It spends no attempt and never sets `model_deferred_until`.

The scope is the installation GitHub counts the push token against. P-71 asked as the Maintainer's own login, a person's token. The push sends the Role App's installation token (`adapters/identity.py`), and each Role has its own App, so the Role and the owner name it.

Limits: no Role pushes yet. A pass that reads the run records short waits on nothing it can read, and every Run defers then. A reset GitHub moves earlier is waited out to the old one.

## Why

A rate limit is GitHub's, not the item's or the model's. Run again at once, each push spends a Run, bounded only by the cost ceiling; under `capacity` every model Run would wait five hours.

The reset is no outside text reaching a decision. It is a number, never text, and reaches only the Controller's clamp, never a Kernel reason. The clamp bounds the worst a wrong value does: a wait of at least `least_seconds` and at most `most_seconds`.

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
