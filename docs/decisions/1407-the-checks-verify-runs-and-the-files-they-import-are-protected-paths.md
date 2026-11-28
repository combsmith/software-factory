# 1407. The checks verify runs and the files they import are protected paths

Status: accepted. 2026-11-28, the Solution Architect via the Factory Builder; issue 1377; narrows record 0188, and changes the rows "What stays" and "The limit: one hop" of record 0240.

## Decision

Every check that verify runs joins the protected list in `config/hooks.json`: `check_apps`, `check_authority`, `check_context`, `check_decisions`, `check_examples`, `check_gate_sets`, `check_lifecycle`, `check_purity`, `check_release`, `check_rulesets` and `check_trials`. So do `tools/jsonschema_lite.py` and `tools/eval_result.py`, which the checks import. Each is listed at any suffix, with a package at its name, as record 0240 lists its checks. `tools/check_decisions.py` leaves the reported list.

This narrows record 0188's row "What is pushed" by these names: a Role's push of one is refused. A Role may still push what no list holds, such as `tools/mutants.py`, `tools/mutants_of/` and most of `kernel/` and `tests/`.

Limits:
- The runner, `tools/mutants.py`, and `tools/mutants_of/` stay pushable, so a patch can still blind the merge group's mutant leg (issue 1388).
- The checks that import `kernel/`, `harness/` or `adapters/` still run in phase 2, after Role code (record 1402).
- Until issue 1377's parts 1 to 3 merge, the checks share one process, so a patch to `kernel/` or `tools/mutants_of/` can still end it.

## Why

A push could change most of the checks in the checks' processes, for example with `os._exit(0)` atop `tools/check_lifecycle.py`. Running each check in its own process bounds that to one check; protecting the files closes it. Record 0240 kept the list to one hop for the cost of asking; the checks themselves are now worth it. Running the base's checks against the head could take them off the list later (issue 1387).

## Boundaries

| Boundary | Check |
|---|---|
| Each check verify runs, and each file of tools/ the checks import, is refused at a Role's push, at any suffix | `tests/test_apply.py::Push.test_the_checks_that_hold_a_trust_boundary_are_on_the_repos_own_list`, `tests/test_hooks.py::test_every_protected_path_asks_for_every_edit_tool_in_every_tree`, `config/hooks.json`, mutant: "tools/check_lifecycle.py is pushed by a Role at another suffix" |
| A package at the name of one is refused too | `tests/test_apply.py::Push.test_the_checks_that_hold_a_trust_boundary_are_on_the_repos_own_list`, `config/hooks.json`, mutant: "a package that shadows tools/check_examples.py is pushed by a Role" |
